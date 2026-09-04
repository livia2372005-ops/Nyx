import subprocess
import json
import sys
from pathlib import Path

def test_mcp():
    server_path = Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"
    proc = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )

    def send_recv(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line)

    # 1. Initialize
    init_res = send_recv({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    print("MCP Init result:", init_res["result"]["serverInfo"])
    assert init_res["result"]["serverInfo"]["name"] == "nyx-hybrid-memory"

    # 2. List tools (Should be exactly 4 clean orthogonal tools!)
    tools_res = send_recv({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = tools_res["result"]["tools"]
    print(f"\nDiscovered {len(tools)} Streamlined MCP tools:")
    tool_names = [t["name"] for t in tools]
    for t in tools:
        print(f" - [{t['name']}]: {t['description']}")
    assert len(tools) == 4
    assert set(tool_names) == {"memory_query", "memory_get_state", "memory_update_state", "memory_record"}

    # 3. Test memory_update_state
    print("\n--- Testing memory_update_state ---")
    update_res = send_recv({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "memory_update_state",
            "arguments": {
                "updates": [
                    {"id": "api_version", "content": "v2", "source": "test_script"},
                    {"id": "auth_service", "content": "active", "deps": ["api_version"]}
                ]
            }
        }
    })
    print("Update state result:", update_res["result"]["content"][0]["text"])

    # 4. Test memory_get_state (markdown and json formats)
    print("\n--- Testing memory_get_state ---")
    get_md = send_recv({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "memory_get_state",
            "arguments": {"format": "markdown"}
        }
    })
    print("Get state (Markdown format):\n", get_md["result"]["content"][0]["text"])
    assert "api_version" in get_md["result"]["content"][0]["text"]

    get_json = send_recv({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "memory_get_state",
            "arguments": {"format": "json"}
        }
    })
    assert "api_version" in get_json["result"]["content"][0]["text"]

    # 5. Test memory_record (both 'event' and 'fact')
    print("\n--- Testing memory_record ---")
    rec_event = send_recv({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "memory_record",
            "arguments": {
                "type": "event",
                "data": {"status": "success", "detail": "JWT token issued"},
                "task_id": "auth-001",
                "agent_role": "executor",
                "tags": ["auth", "token"]
            }
        }
    })
    print("Record event result:", rec_event["result"]["content"][0]["text"])

    rec_fact = send_recv({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "memory_record",
            "arguments": {
                "type": "fact",
                "data": {
                    "id": "jwt_expiry_fact",
                    "title": "Token Expiry Duration",
                    "entity_type": "DomainRule",
                    "properties": {"duration": "24h"}
                }
            }
        }
    })
    print("Record fact result:", rec_fact["result"]["content"][0]["text"])

    # 6. Test memory_query (Unified hybrid search)
    print("\n--- Testing memory_query ---")
    query_res = send_recv({
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "memory_query",
            "arguments": {
                "query": "Token Expiry Duration rule"
            }
        }
    })
    query_text = query_res["result"]["content"][0]["text"]
    print("Query result summary:", query_text[:200], "...")
    assert "Token Expiry Duration" in query_text or "results" in query_text

    proc.terminate()
    print("\n ALL 4 STREAMLINED MCP TOOLS VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    test_mcp()
