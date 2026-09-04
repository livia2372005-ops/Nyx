import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "nyx_memory.db"

def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path: Path | str | None = None):
    conn = get_connection(db_path)
    with conn:
        # 1. State Units (StateMem)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state_units (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                priority INTEGER DEFAULT 3,
                source TEXT,
                deps TEXT DEFAULT '[]',
                status TEXT DEFAULT 'active',
                updated_at TEXT NOT NULL,
                superseded_by TEXT
            );
        """)
        
        # 2. Episodic Events
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_events (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                task_id TEXT,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                agent_role TEXT,
                tags TEXT DEFAULT '[]'
            );
        """)

        # Episodic FTS5 index
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(
                    id UNINDEXED,
                    content,
                    tags,
                    event_type
                );
            """)
        except sqlite3.OperationalError:
            # Fallback if FTS5 not compiled in sqlite
            pass

        # 3. Semantic Graph: Nodes & Edges
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_nodes (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                title TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                rel_type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                PRIMARY KEY (source_id, target_id, rel_type),
                FOREIGN KEY (source_id) REFERENCES semantic_nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES semantic_nodes(id) ON DELETE CASCADE
            );
        """)
        
        # Indexes for fast querying
        conn.execute("CREATE INDEX IF NOT EXISTS idx_state_status ON state_units(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_time ON episodic_events(timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_task ON episodic_events(task_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_type ON semantic_nodes(entity_type);")

    conn.close()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
