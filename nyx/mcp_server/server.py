import sys
import json
import os
import argparse
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from nyx.mcp_server.db import init_db, DEFAULT_DB_PATH
    from nyx.mcp_server.state_mem import StateMemEngine
    from nyx.mcp_server.episodic import EpisodicMemoryEngine
    from nyx.mcp_server.semantic import SemanticMemoryEngine
    from nyx.mcp_server.hybrid_router import HybridRouter
else:
    from .db import init_db, DEFAULT_DB_PATH
    from .state_mem import StateMemEngine
    from .episodic import EpisodicMemoryEngine
    from .semantic import SemanticMemoryEngine
    from .hybrid_router import HybridRouter

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TOOLS_DEFINITIONS = [
    {
        "name": "memory_query",
        "description": "Unified hybrid retrieval tool. Automatically queries Vector Store, Knowledge Graph, and Episodic Events using intelligent intent routing and Reciprocal Rank Fusion (RRF).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search question, topic, or entity name"
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": "Maximum items to return"
                },
                "scope": {
                    "type": "string",
                    "enum": ["all", "semantic", "episodic"],
                    "default": "all",
                    "description": "Search scope: 'all' (hybrid vector+graph), 'semantic' (rules/architecture), or 'episodic' (past task history)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_get_state",
        "description": "Retrieve current valid state from StateMem dependency graph G=(U,E). Highlights any [!] [NEEDS_RECHECK] flags to eliminate State Drift.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_unit_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of state unit IDs. If omitted, retrieves all active state units."
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "default": "markdown",
                    "description": "Output format: 'markdown' (formatted prompt block with warnings) or 'json' (raw dictionary)"
                }
            }
        }
    },
    {
        "name": "memory_update_state",
        "description": "Insert or update state units in StateMem. Automatically propagates [!] [NEEDS_RECHECK] downstream to all dependent units to prevent State Drift. Enforces cycle detection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "description": "List of state unit objects to upsert.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique state key (e.g. 'auth_method', 'db_schema_version')"},
                            "content": {"description": "Current value or structured dictionary"},
                            "priority": {"type": "integer", "description": "Priority 1 (high) to 5 (low)"},
                            "source": {"type": "string", "description": "Origin file/task (e.g. 'plan.md#L12')"},
                            "deps": {"type": "array", "items": {"type": "string"}, "description": "IDs of state units this unit depends on"},
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
        "name": "memory_record",
        "description": "Record information into memory: either log an execution event/milestone (type='event') or promote a verified fact/rule to the Semantic Knowledge Graph (type='fact').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["event", "fact"],
                    "description": "'event' for task execution logs/milestones; 'fact' for verified rules or architectural decisions"
                },
                "data": {
                    "type": "object",
                    "description": "For 'event': {event_type, content, ...}. For 'fact': {id, title, entity_type, properties, relations, ...}"
                },
                "task_id": {
                    "type": "string",
                    "description": "Associated task ID"
                },
                "agent_role": {
                    "type": "string",
                    "description": "Role of calling agent ('planner', 'executor', 'reviewer')"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional search tags"
                }
            },
            "required": ["type", "data"]
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

    def _log_activity(self, tool_name: str, arguments: dict, result_summary: str, is_error: bool = False):
        try:
            log_dir = Path(__file__).resolve().parent.parent / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            status_badge = "[ERROR]" if is_error else "[OK]"
            entry = f"[{now_local}] {status_badge} TOOL: {tool_name}\n"
            entry += f"   ├── Args: {json.dumps(arguments, ensure_ascii=False)}\n"
            entry += f"   └── Result: {result_summary}\n\n"

            with open(log_dir / "activity.log", "a", encoding="utf-8") as f:
                f.write(entry)

            json_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "local_time": now_local,
                "tool": tool_name,
                "arguments": arguments,
                "summary": result_summary,
                "is_error": is_error
            }
            with open(log_dir / "activity.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(json_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def handle_call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            # 1. UNIFIED QUERY
            if name == "memory_query":
                query_text = arguments["query"]
                limit = arguments.get("limit", 5)
                scope = arguments.get("scope", "all")

                if scope == "episodic":
                    res = self.episodic.query_events(query=query_text, limit=limit)
                    summary = f"Episodic query '{query_text}' -> {len(res)} events"
                elif scope == "semantic":
                    res = self.semantic.query_semantic(query=query_text, limit=limit)
                    summary = f"Semantic query '{query_text}' -> {len(res)} nodes"
                else:
                    res = self.hybrid_router.query(query=query_text, limit=limit)
                    summary = f"Hybrid query '{query_text}' -> Mode: {res.get('executed_mode')}, Matches: {res.get('total_matches')}"

                self._log_activity(name, arguments, summary)
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            # 2. GET STATE (with Markdown / JSON formatting)
            elif name == "memory_get_state":
                fmt = arguments.get("format", "markdown")
                unit_ids = arguments.get("state_unit_ids")

                if fmt == "json":
                    res = self.state_mem.get_state(unit_ids=unit_ids, include_all=False)
                    drift_count = sum(1 for u in res.values() if u["status"] == "needs_recheck")
                    summary = f"Fetched {len(res)} state units (JSON), Drift flags: {drift_count}"
                    self._log_activity(name, arguments, summary)
                    return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}
                else:
                    rendered = self.state_mem.render_state_block(unit_ids=unit_ids)
                    has_drift = "[NEEDS_RECHECK" in rendered
                    summary = f"Rendered state block (Markdown). State drift detected: {has_drift}"
                    self._log_activity(name, arguments, summary)
                    return {"content": [{"type": "text", "text": rendered}]}

            # 3. UPDATE STATE (StateMem Invalidation & Cycle Detection)
            elif name == "memory_update_state":
                res = self.state_mem.update_state(arguments.get("updates", []))
                summary = f"Updated {res.get('updated_count')} units. Invalidated downstream: {res.get('invalidated_ids')}"
                self._log_activity(name, arguments, summary)
                return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

            # 4. RECORD (Events or Facts)
            elif name == "memory_record":
                rec_type = arguments["type"]
                data = arguments["data"]
                task_id = arguments.get("task_id")
                agent_role = arguments.get("agent_role")
                tags = arguments.get("tags")

                if rec_type == "event":
                    event_type = data.get("event_type", "milestone")
                    content = data.get("content", data)
                    eid = self.episodic.log_event(
                        event_type=event_type,
                        content=content,
                        task_id=task_id,
                        agent_role=agent_role,
                        tags=tags
                    )
                    summary = f"Logged episodic event '{event_type}' (id={eid}) by role '{agent_role}'"
                    self._log_activity(name, arguments, summary)
                    return {"content": [{"type": "text", "text": json.dumps({"success": True, "event_id": eid, "type": "event"})}]}

                elif rec_type == "fact":
                    facts = [data] if (isinstance(data, dict) and ("id" in data or "key" in data)) else data.get("facts", [data])
                    res = self.semantic.promote_facts(facts)
                    summary = f"Promoted {res.get('promoted_count')} facts to Knowledge Graph: {res.get('promoted_ids')}"
                    self._log_activity(name, arguments, summary)
                    return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

                else:
                    msg = f"Unsupported record type: {rec_type}. Must be 'event' or 'fact'."
                    self._log_activity(name, arguments, msg, is_error=True)
                    return {
                        "isError": True,
                        "content": [{"type": "text", "text": msg}]
                    }

            else:
                msg = f"Unknown tool: {name}. Available tools: memory_query, memory_get_state, memory_update_state, memory_record"
                self._log_activity(name, arguments, msg, is_error=True)
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": msg}]
                }

        except Exception as e:
            err_msg = f"Error executing {name}: {str(e)}"
            self._log_activity(name, arguments, err_msg, is_error=True)
            return {
                "isError": True,
                "content": [{"type": "text", "text": err_msg}]
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
                            "version": "2.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
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
    parser = argparse.ArgumentParser(description="Nyx Hybrid Memory MCP Server (Streamlined Edition)")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite memory database")
    args = parser.parse_args()

    server = NyxMcpServer(db_path=args.db)
    server.run_stdio()

if __name__ == "__main__":
    main()
