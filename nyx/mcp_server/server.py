import sys
import json
import os
import argparse
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from nyx.mcp_server.db import init_db, DEFAULT_DB_PATH
    from nyx.mcp_server.state_mem import StateMemEngine
    from nyx.mcp_server.episodic import EpisodicMemoryEngine
    from nyx.mcp_server.semantic import SemanticMemoryEngine
    from nyx.mcp_server.hybrid_router import HybridRouter
    from nyx.scripts.git_ops import sign_context_pack, verify_context_pack
else:
    from .db import init_db, DEFAULT_DB_PATH
    from .state_mem import StateMemEngine
    from .episodic import EpisodicMemoryEngine
    from .semantic import SemanticMemoryEngine
    from .hybrid_router import HybridRouter
    from ..scripts.git_ops import sign_context_pack, verify_context_pack

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TOOLS_DEFINITIONS = [
    {
        "name": "memory_get_state",
        "description": "Get current valid state for state unit IDs or all active state units. Returns values, dependencies, and flags any units needing recheck.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_unit_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of state unit IDs to retrieve. If omitted, retrieves all active units."
                },
                "include_all": {
                    "type": "boolean",
                    "description": "If true, also includes superseded historical state units."
                }
            }
        }
    },
    {
        "name": "memory_update_state",
        "description": "Insert or update state units in StateMem. Automatically propagates 'needs_recheck' to all dependent units downstream to eliminate State Drift.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "description": "List of state unit objects to upsert.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique key (e.g. 'auth_method', 'db_schema_version')"},
                            "content": {"description": "Current value or structured dictionary"},
                            "priority": {"type": "integer", "description": "Priority 1 (highest) to 5 (lowest)"},
                            "source": {"type": "string", "description": "Origin file/commit (e.g. 'plan.md#L12')"},
                            "deps": {"type": "array", "items": {"type": "string"}, "description": "IDs of parent units this unit depends on"},
                            "status": {"type": "string", "enum": ["active", "superseded", "needs_recheck"]}
                        },
                        "required": ["id", "content"]
                    }
                }
            },
            "required": ["updates"]
        }
    },
    {
        "name": "memory_render_state_block",
        "description": "Render a cohesive markdown block of current active states with warning flags for invalidated dependencies, suitable for prompt inclusion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_unit_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional specific unit IDs to render."
                }
            }
        }
    },
    {
        "name": "memory_query_episodic",
        "description": "Query episodic memory for past events, task execution reports, logs, and historical context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term or keyword (uses FTS5)"},
                "limit": {"type": "integer", "default": 5},
                "task_id": {"type": "string", "description": "Filter by task ID"},
                "session_id": {"type": "string", "description": "Filter by session ID"},
                "agent_role": {"type": "string", "description": "Filter by role ('planner', 'executor', 'reviewer')"}
            }
        }
    },
    {
        "name": "memory_log_episodic",
        "description": "Record a timestamped episodic event, step result, or milestone into the Event Store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string", "description": "Event type (e.g. 'task_executed', 'plan_created', 'drift_detected')"},
                "content": {"description": "Structured data or markdown text of the event"},
                "task_id": {"type": "string", "description": "Associated task ID"},
                "agent_role": {"type": "string", "description": "Role of the executing agent"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "List of search tags"}
            },
            "required": ["event_type", "content"]
        }
    },
    {
        "name": "memory_query_semantic",
        "description": "Query semantic memory (Knowledge Graph + Rules) for architectural decisions, domain rules, and entity relationships.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term to match node titles and properties"},
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter (e.g. ['ArchitectureDecision', 'DomainRule', 'Convention'])"
                },
                "limit": {"type": "integer", "default": 5},
                "include_relations": {"type": "boolean", "default": True, "description": "Include 1-hop connected graph relations"}
            }
        }
    },
    {
        "name": "memory_promote_to_semantic",
        "description": "Promote verified facts, rules, or architectural decisions into permanent Semantic Knowledge Graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "description": "List of facts to promote.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Identifier for the semantic node"},
                            "entity_type": {"type": "string", "description": "Node type (ArchitectureDecision, DomainRule, Fact)"},
                            "title": {"type": "string", "description": "Short human-readable title"},
                            "properties": {"type": "object", "description": "Detailed properties/rules"},
                            "relations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "target_id": {"type": "string"},
                                        "rel_type": {"type": "string"}
                                    },
                                    "required": ["target_id", "rel_type"]
                                }
                            }
                        },
                        "required": ["id", "title"]
                    }
                }
            },
            "required": ["facts"]
        }
    },
    {
        "name": "memory_hybrid_query",
        "description": "Intelligent hybrid retrieval router. Classifies intent (vector similarity vs graph traversal) and fuses results using Reciprocal Rank Fusion (RRF).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or natural language question"},
                "limit": {"type": "integer", "default": 5},
                "mode": {
                    "type": "string",
                    "enum": ["auto", "vector_path", "graph_path", "hybrid_fusion"],
                    "description": "Optional force execution mode (default: 'auto')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_sign_context_pack",
        "description": "Cryptographically sign a ContextPack dictionary with HMAC-SHA256 so Executor can verify integrity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context_pack": {"type": "object", "description": "ContextPack data to sign"}
            },
            "required": ["context_pack"]
        }
    },
    {
        "name": "memory_verify_context_pack",
        "description": "Verify cryptographic signature of a ContextPack to ensure it was created by Planner without tampering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context_pack": {"type": "object", "description": "ContextPack data"},
                "signature": {"type": "string", "description": "Expected cryptographic signature"}
            },
            "required": ["context_pack", "signature"]
        }
    }
]

class NyxMcpServer:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        init_db(self.db_path)
        self.state_mem = StateMemEngine(self.db_path)
        self.episodic = EpisodicMemoryEngine(self.db_path)
        self.semantic = SemanticMemoryEngine(self.db_path)
        self.hybrid_router = HybridRouter(self.db_path)

    def handle_call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "memory_get_state":
                res = self.state_mem.get_state(
                    unit_ids=arguments.get("state_unit_ids"),
                    include_all=arguments.get("include_all", False)
                )
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            elif name == "memory_update_state":
                res = self.state_mem.update_state(arguments.get("updates", []))
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            elif name == "memory_render_state_block":
                rendered = self.state_mem.render_state_block(unit_ids=arguments.get("state_unit_ids"))
                return {"content": [{"type": "text", "text": rendered}]}

            elif name == "memory_query_episodic":
                res = self.episodic.query_events(
                    query=arguments.get("query", ""),
                    limit=arguments.get("limit", 5),
                    task_id=arguments.get("task_id"),
                    session_id=arguments.get("session_id"),
                    agent_role=arguments.get("agent_role")
                )
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            elif name == "memory_log_episodic":
                eid = self.episodic.log_event(
                    event_type=arguments["event_type"],
                    content=arguments["content"],
                    task_id=arguments.get("task_id"),
                    agent_role=arguments.get("agent_role"),
                    tags=arguments.get("tags")
                )
                return {"content": [{"type": "text", "text": json.dumps({"success": True, "event_id": eid})}]}

            elif name == "memory_query_semantic":
                res = self.semantic.query_semantic(
                    query=arguments.get("query", ""),
                    entity_types=arguments.get("entity_types"),
                    limit=arguments.get("limit", 5),
                    include_relations=arguments.get("include_relations", True)
                )
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            elif name == "memory_promote_to_semantic":
                res = self.semantic.promote_facts(arguments.get("facts", []))
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            elif name == "memory_hybrid_query":
                res = self.hybrid_router.query(
                    query=arguments["query"],
                    limit=arguments.get("limit", 5),
                    forced_mode=arguments.get("mode")
                )
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            elif name == "memory_sign_context_pack":
                sig = sign_context_pack(arguments["context_pack"])
                return {"content": [{"type": "text", "text": json.dumps({"signature": sig, "success": True})}]}

            elif name == "memory_verify_context_pack":
                is_valid = verify_context_pack(arguments["context_pack"], arguments["signature"])
                return {"content": [{"type": "text", "text": json.dumps({"valid": is_valid})}]}

            else:
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Unknown tool: {name}"}]
                }
        except Exception as e:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Error executing tool {name}: {str(e)}"}]
            }

    def run_stdio(self):
        """Standard JSON-RPC 2.0 Stdio loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except Exception:
                continue

            msg_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "nyx-hybrid-memory",
                            "version": "1.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
                # No response needed for notification
                pass

            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": TOOLS_DEFINITIONS
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = self.handle_call_tool(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": result
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            elif method == "ping":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {}
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            else:
                if msg_id is not None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}"
                        }
                    }
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Nyx Hybrid Memory MCP Server")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite memory database")
    args = parser.parse_args()

    server = NyxMcpServer(db_path=args.db)
    server.run_stdio()

if __name__ == "__main__":
    main()
