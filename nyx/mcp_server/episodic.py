import json
import uuid
from typing import Any
from pathlib import Path
from .db import get_connection, now_iso
from .vector_store import LocalVectorStore

class EpisodicMemoryEngine:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path
        self.vector_store = LocalVectorStore(db_path)

    def log_event(
        self,
        event_type: str,
        content: Any,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_role: str | None = None,
        tags: list[str] | None = None,
        event_id: str | None = None,
    ) -> str:
        """
        Logs a timestamped episodic event.
        """
        conn = get_connection(self.db_path)
        eid = event_id or str(uuid.uuid4())
        content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else str(content)
        tags_list = tags or []
        tags_json = json.dumps(tags_list)
        now = now_iso()

        with conn:
            conn.execute("""
                INSERT INTO episodic_events (id, session_id, task_id, event_type, content, timestamp, agent_role, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (eid, session_id, task_id, event_type, content_str, now, agent_role, tags_json))

            # Sync with FTS if available
            try:
                conn.execute("""
                    INSERT INTO episodic_fts (id, content, tags, event_type)
                    VALUES (?, ?, ?, ?)
                """, (eid, content_str, " ".join(tags_list), event_type))
            except Exception:
                pass

        conn.close()

        # Index into vector store
        vec_text = f"[{event_type}] {' '.join(tags_list)} {content_str}"
        self.vector_store.upsert(eid, "episodic", vec_text, {
            "event_type": event_type,
            "session_id": session_id,
            "task_id": task_id,
            "agent_role": agent_role
        })

        return eid

    def query_events(
        self,
        query: str = "",
        limit: int = 5,
        session_id: str | None = None,
        task_id: str | None = None,
        agent_role: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Queries episodic events using FTS5 or LIKE pattern matching, ordered by newest first.
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        results = []

        if query.strip():
            # Try FTS first
            try:
                fts_query = f"""
                    SELECT e.*
                    FROM episodic_events e
                    JOIN episodic_fts f ON e.id = f.id
                    WHERE episodic_fts MATCH ?
                    ORDER BY e.timestamp DESC
                    LIMIT ?
                """
                # Clean up query term for FTS
                cleaned_query = " OR ".join(f'"{part}"' for part in query.split() if part)
                cursor.execute(fts_query, (cleaned_query, limit))
                rows = cursor.fetchall()
            except Exception:
                rows = []

            # If FTS returns no rows or errored, fallback to LIKE
            if not rows:
                like_param = f"%{query}%"
                cursor.execute("""
                    SELECT * FROM episodic_events
                    WHERE content LIKE ? OR tags LIKE ? OR event_type LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (like_param, like_param, like_param, limit))
                rows = cursor.fetchall()
        else:
            filters = []
            params = []
            if session_id:
                filters.append("session_id = ?")
                params.append(session_id)
            if task_id:
                filters.append("task_id = ?")
                params.append(task_id)
            if agent_role:
                filters.append("agent_role = ?")
                params.append(agent_role)

            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
            cursor.execute(f"SELECT * FROM episodic_events {where_clause} ORDER BY timestamp DESC LIMIT ?", params + [limit])
            rows = cursor.fetchall()

        for r in rows:
            try:
                parsed_content = json.loads(r["content"])
            except Exception:
                parsed_content = r["content"]
            try:
                parsed_tags = json.loads(r["tags"])
            except Exception:
                parsed_tags = []

            results.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "task_id": r["task_id"],
                "event_type": r["event_type"],
                "content": parsed_content,
                "timestamp": r["timestamp"],
                "agent_role": r["agent_role"],
                "tags": parsed_tags
            })

        conn.close()
        return results
