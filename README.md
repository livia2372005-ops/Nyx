# Nyx: Hybrid Memory Multi-Agent System

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Google%20Antigravity-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Platform" />
  <img src="https://img.shields.io/badge/Architecture-Tri--Agent%20Isolation-8A2BE2?style=for-the-badge" alt="Architecture" />
  <img src="https://img.shields.io/badge/Memory-5--Layer%20Hybrid%20StateMem-00C7B7?style=for-the-badge" alt="Memory" />
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Protocol-Model%20Context%20Protocol%20(MCP)-FF6F00?style=for-the-badge" alt="MCP" />
</p>

---

## Overview

**Nyx** is a production-grade multi-agent autonomous engineering framework specifically engineered for the **Google Antigravity** platform. 

Most long-horizon AI coding systems fail due to two fundamental architectural bottlenecks:
1. **Context Bloat**: Feeding entire codebases and conversation logs into a single context window degrades reasoning and triggers hallucinations.
2. **State Drift**: LLMs reuse outdated assumptions and superseded facts even when new state updates have occurred.

Nyx eliminates both failure modes through a **Tri-Agent Isolated Workflow (Planner $\to$ Executor $\to$ Reviewer)** paired with an active **5-Layer Hybrid Memory Architecture** featuring deterministic dependency invalidation ($G=(U,E)$).

---

## Key Innovations

```
                                  ┌─────────────────────────────────────────┐
                                  │          Antigravity Chat Canvas        │
                                  │             (PLANNER AGENT)             │
                                  └────────────────────┬────────────────────┘
                                                       │
                                 ContextPack (Signed)  │ DAG Tasks (plan.md)
                                                       ▼
                                  ┌─────────────────────────────────────────┐
                                  │      Isolated Antigravity Subagent      │
                                  │             (EXECUTOR AGENT)            │
                                  └────────────────────┬────────────────────┘
                                                       │
                                   report.md + new_facts│ branch: exec/*
                                                       ▼
                                  ┌─────────────────────────────────────────┐
                                  │       Independent Auditor Subagent      │
                                  │             (REVIEWER AGENT)            │
                                  └────────────────────┬────────────────────┘
                                                       │
                                                       │ Verify State Drift & Constraints
                                                       ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       HYBRID MEMORY LAYER (MCP)                                        │
│  ┌────────────────────────┐  ┌────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │ 1. Working Memory      │  │ 2. Episodic Store      │  │ 3. Semantic Knowledge Graph              │  │
│  │    In-context scratch  │  │    Timestamped events  │  │    Nodes (ADRs, Rules) & Edges           │  │
│  │    goal.md, plan.md    │  │    FTS5 + Vector recall│  │    1-hop Subgraph & Fact Promotion       │  │
│  └────────────────────────┘  └────────────────────────┘  └──────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │ 4. StateMem Engine G=(U,E)                         │  │ 5. Git-Native Audit Trail                │  │
│  │    Deterministic Invalidation [!] NEEDS_RECHECK    │  │    Signed Role Commits & Branch Handoffs │  │
│  │    Topological Cycle Detection                     │  │    plans/, executions/, verifications/   │  │
│  └────────────────────────────────────────────────────┘  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1. StateMem Engine (Zero-Drift Architecture)
- Represents system facts and dependencies as a directed acyclic graph $G = (U, E)$.
- When a root state unit changes, a **deterministic propagation algorithm** automatically cascades the `[!] [NEEDS_RECHECK]` flag to all dependent units downstream.
- **Cycle Detection**: Prevents infinite dependency loops during runtime state registration.
- **Zero Token Cost**: Invalidation runs via local graph traversal rather than expensive LLM invocations.

### 2. Local-First Vector Store & Hybrid Router
- **Offline Dense Vectorizer**: Generates subword and character n-gram embeddings locally with cosine similarity ranking.
- **Hybrid Intent Router**: Automatically classifies user queries into:
  - `VECTOR_PATH`: Fast semantic matching for conceptual inquiries.
  - `GRAPH_PATH`: Multi-hop relationship traversal for dependency queries.
  - `HYBRID_FUSION`: Blends both channels using **Reciprocal Rank Fusion (RRF)**.

### 3. ContextPack with Tamper-Evident Signatures
- Subagents (Executors) receive strictly bounded context packages containing only relevant file excerpts.
- Planners cryptographically sign `ContextPack` payloads via HMAC-SHA256, guaranteeing that instructions and file scopes remain unmodified before execution.

### 4. Git-Native Role Segregation
- Each stage commits with dedicated cryptographic identities:
  - `Nyx Planner <agent-planner@nyx.local>` on `plan/*` branches
  - `Nyx Executor <agent-executor@nyx.local>` on `exec/*` branches
  - `Nyx Reviewer <agent-reviewer@nyx.local>` on `main` branch merges

---

## Directory Structure

```text
.
├── AGENTS.md                          # Antigravity Always-On Mandate
├── README.md                          # Documentation
├── .agents/                           # Antigravity Customization Root
│   └── plugins/
│       └── nyx/
│           ├── plugin.json            # Plugin manifest
│           ├── mcp_config.json        # MCP server registration
│           ├── rules/nyx-rules.md     # Invariant rules & drift guardrails
│           └── skills/nyx/SKILL.md    # Multi-agent operations skill
└── nyx/                               # Core Nyx Engine
    ├── NYX.md                         # Master orchestration protocol
    ├── mcp_server/                    # Stdio JSON-RPC 2.0 MCP Server
    │   ├── server.py                  # Protocol dispatcher
    │   ├── state_mem.py               # StateMem G=(U,E) & invalidator
    │   ├── vector_store.py            # Local offline dense vector store
    │   ├── hybrid_router.py           # Intent router & RRF re-ranker
    │   ├── episodic.py                # FTS5 Event store
    │   ├── semantic.py                # Knowledge Graph & fact promotion
    │   └── db.py                      # SQLite storage manager
    ├── memory-git/                    # Git audit trail
    │   ├── plans/                     # DAG plans & ContextPacks
    │   ├── executions/                # Execution reports & logs
    │   ├── verifications/             # Audit verifications
    │   └── semantic/                  # Markdown rule mirrors
    ├── working/                       # Transient scratchpads
    │   ├── goal.md
    │   ├── plan_summary.md
    │   └── recent_results.md
    └── scripts/                       # Utilities & test suites
        ├── init_nyx.py                # Baseline initialization
        ├── git_ops.py                 # Role commits & HMAC signing
        ├── test_memory.py             # Memory engine unit tests
        └── test_mcp_server.py         # MCP protocol end-to-end tests
```

---

## MCP Tools Reference

The Nyx Memory Server exposes 10 standardized MCP tools via stdio:

| Tool Name | Scope | Description |
| :--- | :--- | :--- |
| `memory_get_state` | StateMem | Retrieve current valid state units; highlights `[!] NEEDS_RECHECK` flags |
| `memory_update_state` | StateMem | Insert/update state units; triggers deterministic downstream invalidation |
| `memory_render_state_block` | StateMem | Render human/LLM-readable markdown snapshot of the state graph |
| `memory_query_episodic` | Episodic | Query historical logs, previous task executions, and errors via FTS5 |
| `memory_log_episodic` | Episodic | Record timestamped event milestones into the persistent Event Store |
| `memory_query_semantic` | Semantic | Query Knowledge Graph nodes (ADRs, Domain Rules) and 1-hop relations |
| `memory_promote_to_semantic`| Semantic | Promote verified facts from execution reports to permanent knowledge |
| `memory_hybrid_query` | Hybrid | Route queries between Vector search and Graph traversal with RRF fusion |
| `memory_sign_context_pack` | Security | Compute HMAC-SHA256 signature for bounded task ContextPacks |
| `memory_verify_context_pack`| Security | Verify cryptographic authenticity of ContextPacks before execution |

---

## Getting Started

### 1. Installation
Clone or copy the `nyx/` and `.agents/` directories into your target workspace:

```bash
git clone https://github.com/livia2372005-ops/Nyx.git
```

### 2. Verify Baseline
Run the built-in diagnostic and test scripts to ensure all components and SQLite databases are ready:

```bash
python nyx/scripts/test_memory.py
python nyx/scripts/test_mcp_server.py
```

### 3. Usage with Google Antigravity
With [AGENTS.md](file:///d:/App/Noname/AGENTS.md) residing at the project root, **no special flags or `@` mentions are necessary**.

Simply submit any task through the Antigravity chat interface:
> *"Refactor user authentication to JWT with RS256 signing and update middleware"*

The agent will automatically:
1. Assume the **Planner** role, query active architectural decisions, and draft a DAG plan.
2. Package bounded **ContextPacks** with cryptographic signatures.
3. Spawn isolated **Executors** in fresh context windows to perform surgical code changes.
4. Conduct independent **Reviewer** auditing to ensure zero State Drift before merging into `main`.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
