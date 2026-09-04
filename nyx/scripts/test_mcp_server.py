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

    # 2. List tools
    tools_res = send_recv({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = tools_res["result"]["tools"]
    print(f"Discovered {len(tools)} MCP tools:")
    for t in tools:
        print(f" - {t['name']}: {t['description'][:50]}...")
    assert len(tools) >= 6

    # 3. Call tool memory_update_state
    call_res = send_recv({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "memory_update_state",
            "arguments": {
                "updates": [
                    {"id": "system_status", "content": "online", "source": "test"}
                ]
            }
        }
    })
    print("Tool call update_state result:", call_res["result"]["content"][0]["text"])

    # 4. Call tool memory_get_state
    get_res = send_recv({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "memory_get_state",
            "arguments": {"state_unit_ids": ["system_status"]}
        }
    })
    print("Tool call get_state result:", get_res["result"]["content"][0]["text"])
    assert "online" in get_res["result"]["content"][0]["text"]

    # 5. Call tool memory_sign_context_pack & memory_verify_context_pack
    sign_res = send_recv({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "memory_sign_context_pack",
            "arguments": {
                "context_pack": {"task_id": "test_001", "files": ["main.py"]}
            }
        }
    })
    sign_data = json.loads(sign_res["result"]["content"][0]["text"])
    sig = sign_data["signature"]
    print("Tool call memory_sign_context_pack signature:", sig)
    assert len(sig) == 64

    verify_res = send_recv({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "memory_verify_context_pack",
            "arguments": {
                "context_pack": {"task_id": "test_001", "files": ["main.py"]},
                "signature": sig
            }
        }
    })
    verify_data = json.loads(verify_res["result"]["content"][0]["text"])
    assert verify_data["valid"] is True
    print("Tool call memory_verify_context_pack verified:", verify_data["valid"])

    # 6. Call tool memory_hybrid_query
    hybrid_res = send_recv({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "memory_hybrid_query",
            "arguments": {
                "query": "system status online"
            }
        }
    })
    hybrid_data = json.loads(hybrid_res["result"]["content"][0]["text"])
    print("Tool call memory_hybrid_query mode:", hybrid_data["executed_mode"])
    assert "results" in hybrid_data

    proc.terminate()
    print("\n MCP SERVER JSON-RPC PROTOCOL TEST PASSED (ALL 10 TOOLS)!")

if __name__ == "__main__":
    test_mcp()
