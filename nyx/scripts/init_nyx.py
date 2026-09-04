import sys
import subprocess
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from nyx.mcp_server.db import init_db, DEFAULT_DB_PATH
from nyx.mcp_server.state_mem import StateMemEngine
from nyx.mcp_server.semantic import SemanticMemoryEngine

def init_nyx():
    print("========================================")
    print("  Initializing Nyx Agent System Engine  ")
    print("========================================")

    # 1. Initialize SQLite Memory DB
    print(f"\n1. Initializing Memory DB at: {DEFAULT_DB_PATH}")
    init_db(DEFAULT_DB_PATH)

    state_engine = StateMemEngine(DEFAULT_DB_PATH)
    semantic_engine = SemanticMemoryEngine(DEFAULT_DB_PATH)

    # Seed baseline states if not present
    existing_state = state_engine.get_state()
    if not existing_state:
        print("   -> Seeding baseline State Units...")
        state_engine.update_state([
            {
                "id": "nyx_system_version",
                "content": "1.0.0",
                "priority": 1,
                "source": "nyx/scripts/init_nyx.py",
                "deps": [],
                "status": "active"
            },
            {
                "id": "agent_architecture",
                "content": "Tri-Agent (Planner -> Executor -> Reviewer)",
                "priority": 1,
                "source": "kientruc.md",
                "deps": [],
                "status": "active"
            }
        ])

    # Seed baseline semantic knowledge
    existing_sem = semantic_engine.query_semantic(limit=1)
    if not existing_sem:
        print("   -> Seeding baseline Semantic Knowledge & Rules...")
        semantic_engine.add_or_update_node(
            "adr_001_tri_agent",
            "ArchitectureDecision",
            "ADR-001: Tri-Agent Role Isolation",
            {"status": "Accepted", "roles": ["planner", "executor", "reviewer"]}
        )
        semantic_engine.add_or_update_node(
            "adr_002_statemem",
            "ArchitectureDecision",
            "ADR-002: StateMem Dependency Invalidation",
            {"status": "Accepted", "model": "G=(U,E)"}
        )
        semantic_engine.add_or_update_node(
            "rule_context_pack",
            "DomainRule",
            "Rule-001: Context Bounding via ContextPack",
            {"target": "Executor", "constraint": "No full repo bloat"}
        )
        semantic_engine.add_or_update_node(
            "rule_state_drift",
            "DomainRule",
            "Rule-003: State Drift Prohibition",
            {"constraint": "No needs_recheck units allowed in final verification"}
        )
        semantic_engine.add_edge("adr_002_statemem", "rule_state_drift", "CONSTRAINS")

    # 2. Check Git repository
    print("\n2. Checking Git repository baseline...")
    git_dir = root_dir / ".git"
    if not git_dir.exists():
        print("   -> Initializing local Git repository...")
        try:
            subprocess.run(["git", "init"], cwd=str(root_dir), check=True, capture_output=True, text=True)
            print("   -> Git repository initialized successfully.")
        except Exception as e:
            print(f"   [!] Warning initializing git: {e}")
    else:
        print("   -> Git repository already active.")

    print("\n[OK] Nyx Hybrid Memory Engine is fully initialized and ready!")
    print("========================================\n")

if __name__ == "__main__":
    init_nyx()
