import json
import sqlite3
from typing import Any
from pathlib import Path
from .db import get_connection, now_iso

class StateMemEngine:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path

    def get_state(self, unit_ids: list[str] | None = None, include_all: bool = False) -> dict[str, Any]:
        """
        Retrieves state units.
        If unit_ids is provided, retrieves only those units.
        If include_all is False, only returns units with status 'active' or 'needs_recheck'.
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        
        if unit_ids:
            placeholders = ",".join("?" for _ in unit_ids)
            query = f"SELECT * FROM state_units WHERE id IN ({placeholders})"
            params = list(unit_ids)
            if not include_all:
                query += " AND status IN ('active', 'needs_recheck')"
            cursor.execute(query, params)
        else:
            if include_all:
                cursor.execute("SELECT * FROM state_units ORDER BY priority ASC, updated_at DESC")
            else:
                cursor.execute("SELECT * FROM state_units WHERE status IN ('active', 'needs_recheck') ORDER BY priority ASC, updated_at DESC")
                
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            result[r["id"]] = {
                "id": r["id"],
                "content": json.loads(r["content"]) if r["content"] else None,
                "priority": r["priority"],
                "source": r["source"],
                "deps": json.loads(r["deps"]) if r["deps"] else [],
                "status": r["status"],
                "updated_at": r["updated_at"],
                "superseded_by": r["superseded_by"],
            }
        conn.close()
        return result

    def update_state(self, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Inserts or updates state units and propagates invalidation to dependent units.
        Dependency rule: if unit B has deps=[A], then B depends on A.
        When A changes, B is marked 'needs_recheck'.
        """
        conn = get_connection(self.db_path)
        now = now_iso()
        updated_ids = []
        invalidated_ids = set()

        with conn:
            for item in updates:
                unit_id = item["id"]
                new_content = item.get("content")
                content_json = json.dumps(new_content)
                priority = item.get("priority", 3)
                source = item.get("source", "unknown")
                deps = item.get("deps", [])
                deps_json = json.dumps(deps)
                status = item.get("status", "active")
                superseded_by = item.get("superseded_by")

                # Cycle Detection
                if deps:
                    self._check_for_cycle(conn, unit_id, deps)

                # Check if unit already exists
                cur = conn.execute("SELECT content, status FROM state_units WHERE id = ?", (unit_id,))
                existing = cur.fetchone()
                
                content_changed = False
                if existing:
                    old_content = existing["content"]
                    old_status = existing["status"]
                    if old_content != content_json or old_status != status or status == "superseded":
                        content_changed = True
                    
                    conn.execute("""
                        UPDATE state_units
                        SET content = ?, priority = ?, source = ?, deps = ?, status = ?, updated_at = ?, superseded_by = ?
                        WHERE id = ?
                    """, (content_json, priority, source, deps_json, status, now, superseded_by, unit_id))
                else:
                    content_changed = True
                    conn.execute("""
                        INSERT INTO state_units (id, content, priority, source, deps, status, updated_at, superseded_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (unit_id, content_json, priority, source, deps_json, status, now, superseded_by))

                updated_ids.append(unit_id)

                # If content changed or was marked superseded, propagate invalidation
                if content_changed:
                    dependent_units = self._propagate_invalidation(conn, unit_id, now)
                    invalidated_ids.update(dependent_units)

        conn.close()
        return {
            "success": True,
            "updated_count": len(updated_ids),
            "updated_ids": updated_ids,
            "invalidated_count": len(invalidated_ids),
            "invalidated_ids": list(invalidated_ids)
        }

    def _propagate_invalidation(self, conn: sqlite3.Connection, parent_id: str, timestamp: str) -> set[str]:
        """
        Traverses dependency graph downstream: finds all units that depend on parent_id.
        Sets their status to 'needs_recheck'.
        """
        cur = conn.execute("SELECT id, deps, status FROM state_units WHERE status != 'superseded'")
        all_units = cur.fetchall()

        # Build adjacency: parent -> list of children (units whose deps contain parent)
        children_map: dict[str, list[str]] = {}
        for row in all_units:
            u_id = row["id"]
            try:
                u_deps = json.loads(row["deps"]) if row["deps"] else []
            except Exception:
                u_deps = []
            for dep in u_deps:
                children_map.setdefault(dep, []).append(u_id)

        # BFS / Queue to find all reachable downstream dependents
        invalidated = set()
        queue = [parent_id]
        visited = {parent_id}

        while queue:
            current = queue.pop(0)
            direct_children = children_map.get(current, [])
            for child in direct_children:
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
                    invalidated.add(child)

        # Update status in DB
        if invalidated:
            placeholders = ",".join("?" for _ in invalidated)
            conn.execute(f"""
                UPDATE state_units
                SET status = 'needs_recheck', updated_at = ?
                WHERE id IN ({placeholders}) AND status = 'active'
            """, [timestamp] + list(invalidated))

        return invalidated

    def _check_for_cycle(self, conn: sqlite3.Connection, unit_id: str, new_deps: list[str]):
        """
        Ensures that making unit_id depend on new_deps will not create a circular dependency.
        A cycle exists if unit_id is reachable by following the dependencies of any dep in new_deps.
        """
        cur = conn.execute("SELECT id, deps FROM state_units WHERE status != 'superseded'")
        all_units = {}
        for row in cur.fetchall():
            try:
                all_units[row["id"]] = json.loads(row["deps"]) if row["deps"] else []
            except Exception:
                all_units[row["id"]] = []

        for dep in new_deps:
            if dep == unit_id:
                raise ValueError(f"Self-dependency error: unit '{unit_id}' cannot depend on itself.")

            queue = [dep]
            visited = {dep}
            while queue:
                curr = queue.pop(0)
                if curr == unit_id:
                    raise ValueError(f"Cyclic dependency error: unit '{unit_id}' cannot depend on '{dep}' as it creates a circular dependency loop.")
                for next_dep in all_units.get(curr, []):
                    if next_dep not in visited:
                        visited.add(next_dep)
                        queue.append(next_dep)

    def render_state_block(self, unit_ids: list[str] | None = None) -> str:
        """
        Renders a cohesive markdown block of the state for LLM prompts.
        Flags any invalidated state units with [NEEDS_RECHECK].
        """
        states = self.get_state(unit_ids=unit_ids, include_all=False)
        if not states:
            return "No active state units recorded."

        lines = ["### [Nyx Current State Graph Snapshot]"]
        for uid, val in sorted(states.items(), key=lambda x: (x[1]["priority"], x[0])):
            status_flag = ""
            if val["status"] == "needs_recheck":
                status_flag = " [!] [NEEDS_RECHECK - Dependency invalidated!]"
            
            content_str = json.dumps(val["content"], ensure_ascii=False) if isinstance(val["content"], (dict, list)) else str(val["content"])
            deps_str = f" (deps: {', '.join(val['deps'])})" if val["deps"] else ""
            lines.append(f"- **`{uid}`**{status_flag}: `{content_str}`{deps_str} [source: {val['source']}]")

        return "\n".join(lines)
