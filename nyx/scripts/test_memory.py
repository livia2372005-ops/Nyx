import sys
import os
import json
import tempfile
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from nyx.mcp_server.db import init_db
from nyx.mcp_server.state_mem import StateMemEngine
from nyx.mcp_server.episodic import EpisodicMemoryEngine
from nyx.mcp_server.semantic import SemanticMemoryEngine

def run_tests():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_nyx.db"
        print(f"Initializing test db at {test_db}...")
        init_db(test_db)

        # 1. Test StateMem Engine
        print("\n--- Testing StateMem Engine ---")
        sm = StateMemEngine(test_db)
        
        # Insert base state units
        res = sm.update_state([
            {"id": "auth_method", "content": "session", "priority": 1, "source": "plan.md#L10"},
            {"id": "session_store", "content": "redis", "priority": 2, "source": "plan.md#L11", "deps": ["auth_method"]},
            {"id": "auth_middleware", "content": "session_mw", "priority": 2, "source": "plan.md#L12", "deps": ["session_store"]}
        ])
        print("Initial state insert:", res)
        assert res["updated_count"] == 3
        
        state_snapshot = sm.get_state()
        print("Active state units:", list(state_snapshot.keys()))
        assert state_snapshot["auth_method"]["status"] == "active"
        assert state_snapshot["session_store"]["status"] == "active"
        assert state_snapshot["auth_middleware"]["status"] == "active"

        # Now update auth_method -> JWT (This should trigger invalidation downstream!)
        print("\nUpdating auth_method to 'jwt'...")
        update_res = sm.update_state([
            {"id": "auth_method", "content": "jwt", "source": "exec/task2#L5"}
        ])
        print("Update result:", update_res)
        assert update_res["invalidated_count"] == 2
        assert "session_store" in update_res["invalidated_ids"]
        assert "auth_middleware" in update_res["invalidated_ids"]

        # Verify statuses after propagation
        updated_state = sm.get_state()
        print("State after update:")
        print("auth_method status:", updated_state["auth_method"]["status"], "content:", updated_state["auth_method"]["content"])
        print("session_store status:", updated_state["session_store"]["status"])
        print("auth_middleware status:", updated_state["auth_middleware"]["status"])
        assert updated_state["session_store"]["status"] == "needs_recheck"
        assert updated_state["auth_middleware"]["status"] == "needs_recheck"

        # Render prompt block
        prompt_block = sm.render_state_block()
        print("\nRendered prompt block:")
        print(prompt_block)
        assert "NEEDS_RECHECK" in prompt_block

        # 2. Test Episodic Memory
        print("\n--- Testing Episodic Memory ---")
        ep = EpisodicMemoryEngine(test_db)
        e1 = ep.log_event("plan_created", {"plan": "auth refactor"}, task_id="task-001", agent_role="planner", tags=["auth", "refactor"])
        e2 = ep.log_event("task_executed", {"status": "success", "files": ["auth.py"]}, task_id="task-001", agent_role="executor", tags=["auth", "jwt"])
        print(f"Logged events: {e1}, {e2}")

        search_res = ep.query_events(query="refactor", limit=5)
        print(f"Query 'refactor' found {len(search_res)} events:")
        for r in search_res:
            print(f"  [{r['timestamp']}] {r['agent_role']} - {r['event_type']} - tags: {r['tags']}")
        assert len(search_res) >= 1

        # 3. Test Semantic Memory
        print("\n--- Testing Semantic Memory ---")
        sem = SemanticMemoryEngine(test_db)
        sem.add_or_update_node("jwt_rule", "DomainRule", "JWT Expiration Policy", {"expiry": "24h"})
        sem.add_or_update_node("sec_policy", "ArchitectureDecision", "Zero Trust Auth", {"rationale": "Security first"})
        sem.add_edge("sec_policy", "jwt_rule", "CONSTRAINS")

        query_sem = sem.query_semantic(query="JWT", include_relations=True)
        print(f"Semantic query 'JWT' found {len(query_sem)} nodes:")
        for node in query_sem:
            print(f"  Node: {node['title']} ({node['entity_type']}) - relations: {node['relations']}")
        assert len(query_sem) == 1
        assert query_sem[0]["relations"][0]["rel_type"] == "CONSTRAINS"

        # Test promotion
        promo_res = sem.promote_facts([
            {"id": "extracted_auth_fact", "entity_type": "Fact", "title": "Token Signing Algorithm", "properties": {"algo": "HS256"}}
        ])
        print("Fact promotion result:", promo_res)
        assert promo_res["promoted_count"] == 1

        # 4. Test Cycle Detection in StateMem
        print("\n--- Testing Cycle Detection ---")
        cycle_detected = False
        try:
            # auth_method is an ancestor of auth_middleware. Making auth_method depend on auth_middleware creates a cycle!
            sm.update_state([
                {"id": "auth_method", "content": "cyclic_val", "deps": ["auth_middleware"]}
            ])
        except ValueError as ve:
            cycle_detected = True
            print("Cycle successfully caught:", ve)
        assert cycle_detected, "Cycle detection should have raised ValueError!"

        # 5. Test Local Vector Store
        print("\n--- Testing Local Vector Store ---")
        from nyx.mcp_server.vector_store import LocalVectorStore
        vs = LocalVectorStore(test_db)
        vec_search = vs.search("authentication JWT token expiration", top_k=3)
        print(f"Vector search returned {len(vec_search)} matches:")
        for v in vec_search:
            print(f"  - [{v['namespace']}] score: {v['score']} id: {v['id']}")
        assert len(vec_search) >= 1

        # 6. Test Hybrid Router (Classification + Graph + RRF)
        print("\n--- Testing Hybrid Router ---")
        from nyx.mcp_server.hybrid_router import HybridRouter
        hr = HybridRouter(test_db)
        
        # Test relational query
        h_res = hr.query("What constraints affect JWT rule?", limit=5)
        print("Hybrid query (relational intent):")
        print("  Classified intent:", h_res["classified_intent"])
        print("  Total matches:", h_res["total_matches"])
        for r in h_res["results"]:
            print(f"  - [{r['source']}] {r['title']} (RRF: {r['rrf_score']}) relations: {len(r['relations'])}")
        assert h_res["total_matches"] >= 1

        # 7. Test Cryptographic ContextPack Signing
        print("\n--- Testing ContextPack Signing ---")
        from nyx.scripts.git_ops import sign_context_pack, verify_context_pack
        pack = {
            "task_id": "auth-refactor-001",
            "files": ["src/auth.py", "tests/test_auth.py"],
            "constraints": ["no breaking change"],
            "state_snapshot": {"auth_method": "jwt"}
        }
        sig = sign_context_pack(pack)
        print("Generated ContextPack signature:", sig)
        assert verify_context_pack(pack, sig) is True
        
        # Verify tampering detection
        tampered_pack = dict(pack)
        tampered_pack["files"] = ["src/auth.py", "malicious_file.py"]
        assert verify_context_pack(tampered_pack, sig) is False
        print("Tampering detection successfully rejected modified pack!")

        print("\n ALL ADVANCED CAPABILITY TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
