import json
from typing import Any
from pathlib import Path
from .db import get_connection, now_iso
from .vector_store import LocalVectorStore

class SemanticMemoryEngine:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path
        self.vector_store = LocalVectorStore(db_path)

    def add_or_update_node(
        self,
        node_id: str,
        entity_type: str,
        title: str,
        properties: dict[str, Any] | None = None
    ) -> str:
        conn = get_connection(self.db_path)
        now = now_iso()
        props_json = json.dumps(properties or {}, ensure_ascii=False)

        with conn:
            cur = conn.execute("SELECT id FROM semantic_nodes WHERE id = ?", (node_id,))
            if cur.fetchone():
                conn.execute("""
                    UPDATE semantic_nodes
                    SET entity_type = ?, title = ?, properties = ?, updated_at = ?
                    WHERE id = ?
                """, (entity_type, title, props_json, now, node_id))
            else:
                conn.execute("""
                    INSERT INTO semantic_nodes (id, entity_type, title, properties, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (node_id, entity_type, title, props_json, now, now))
        conn.close()

        # Index in vector store for conceptual recall
        vec_text = f"[{entity_type}] {title} {props_json}"
        self.vector_store.upsert(node_id, "semantic", vec_text, {
            "entity_type": entity_type,
            "title": title
        })

        return node_id

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None
    ):
        conn = get_connection(self.db_path)
        props_json = json.dumps(properties or {}, ensure_ascii=False)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO semantic_edges (source_id, target_id, rel_type, properties)
                VALUES (?, ?, ?, ?)
            """, (source_id, target_id, rel_type, props_json))
        conn.close()

    def query_semantic(
        self,
        query: str = "",
        entity_types: list[str] | None = None,
        limit: int = 5,
        include_relations: bool = True
    ) -> list[dict[str, Any]]:
        """
        Retrieves matching semantic knowledge nodes and optionally expands their 1-hop relational subgraph.
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        sql = "SELECT * FROM semantic_nodes"
        conditions = []
        params = []

        if entity_types:
            placeholders = ",".join("?" for _ in entity_types)
            conditions.append(f"entity_type IN ({placeholders})")
            params.extend(entity_types)

        if query.strip():
            conditions.append("(title LIKE ? OR properties LIKE ? OR entity_type LIKE ?)")
            q = f"%{query.strip()}%"
            params.extend([q, q, q])

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        nodes = cursor.fetchall()
        results = []

        for row in nodes:
            nid = row["id"]
            try:
                props = json.loads(row["properties"])
            except Exception:
                props = {}

            node_data = {
                "id": nid,
                "entity_type": row["entity_type"],
                "title": row["title"],
                "properties": props,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "relations": []
            }

            if include_relations:
                # 1-hop outbound and inbound edges
                edge_cur = conn.execute("""
                    SELECT e.rel_type, e.target_id, n.title, n.entity_type
                    FROM semantic_edges e
                    JOIN semantic_nodes n ON e.target_id = n.id
                    WHERE e.source_id = ?
                """, (nid,))
                for er in edge_cur.fetchall():
                    node_data["relations"].append({
                        "direction": "outbound",
                        "rel_type": er["rel_type"],
                        "target_id": er["target_id"],
                        "target_title": er["title"],
                        "target_type": er["entity_type"]
                    })

                in_cur = conn.execute("""
                    SELECT e.rel_type, e.source_id, n.title, n.entity_type
                    FROM semantic_edges e
                    JOIN semantic_nodes n ON e.source_id = n.id
                    WHERE e.target_id = ?
                """, (nid,))
                for ir in in_cur.fetchall():
                    node_data["relations"].append({
                        "direction": "inbound",
                        "rel_type": ir["rel_type"],
                        "source_id": ir["source_id"],
                        "source_title": ir["title"],
                        "source_type": ir["entity_type"]
                    })

            results.append(node_data)

        conn.close()
        return results

    def promote_facts(self, facts: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Promotes extracted facts/decisions from task execution to durable Semantic Knowledge.
        Each fact can specify: id, entity_type, title, properties, and optional relations.
        """
        promoted_ids = []
        for fact in facts:
            fid = fact.get("id") or fact.get("key")
            if not fid:
                continue
            etype = fact.get("entity_type", "Fact")
            title = fact.get("title", fid)
            props = fact.get("properties", {})
            if "value" in fact and "value" not in props:
                props["value"] = fact["value"]
            if "source" in fact:
                props["promoted_from"] = fact["source"]

            self.add_or_update_node(fid, etype, title, props)
            promoted_ids.append(fid)

            # Optional relations: list of {target_id, rel_type}
            for rel in fact.get("relations", []):
                if "target_id" in rel and "rel_type" in rel:
                    self.add_edge(fid, rel["target_id"], rel["rel_type"])

        return {
            "success": True,
            "promoted_count": len(promoted_ids),
            "promoted_ids": promoted_ids
        }
