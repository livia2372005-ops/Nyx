import re
from typing import Any
from pathlib import Path
from .db import get_connection
from .vector_store import LocalVectorStore
from .semantic import SemanticMemoryEngine

RELATIONAL_KEYWORDS = {
    # English
    "depends", "depend", "dependent", "affect", "affects", "decides", "decide",
    "relates", "related", "constrains", "constraint", "why", "how", "connection",
    "connected", "impact", "causes", "leads to", "governs",
    # Vietnamese
    "phụ thuộc", "ảnh hưởng", "quy định", "quan hệ", "liên quan", "tại sao",
    "như thế nào", "kết nối", "nguyên nhân", "tác động", "ràng buộc", "chi phối"
}

class HybridRouter:
    """
    Intelligent retrieval router matching kientruc.md specification:
    1. Classify query intent (conceptual vs relational)
    2. Fast path vector lookup for conceptual queries
    3. Graph traversal for relational/impact queries
    4. Reciprocal Rank Fusion (RRF) for composite queries
    """
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = db_path
        self.vector_store = LocalVectorStore(db_path)
        self.semantic_engine = SemanticMemoryEngine(db_path)

    def classify_intent(self, query: str) -> tuple[str, list[str]]:
        """
        Classifies query into: 'VECTOR_PATH', 'GRAPH_PATH', or 'HYBRID_FUSION'.
        Returns (intent_type, detected_entities).
        """
        q_lower = query.lower()

        # Check for relational keywords
        has_relational_intent = any(kw in q_lower for kw in RELATIONAL_KEYWORDS)

        # Detect candidate entities (e.g. PascalCase, snake_case, or words matching known nodes)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, entity_type FROM semantic_nodes")
        known_nodes = cursor.fetchall()
        conn.close()

        detected_entities = []
        for node in known_nodes:
            nid = node["id"].lower()
            ntitle = node["title"].lower()
            if nid in q_lower or (len(ntitle) > 3 and ntitle in q_lower):
                detected_entities.append(node["id"])

        entity_count = len(detected_entities)

        if has_relational_intent or entity_count >= 2:
            if entity_count >= 2 and has_relational_intent:
                return "GRAPH_PATH", detected_entities
            else:
                return "HYBRID_FUSION", detected_entities
        else:
            return "VECTOR_PATH", detected_entities

    def query(self, query: str, limit: int = 5, forced_mode: str | None = None) -> dict[str, Any]:
        intent, entities = self.classify_intent(query)
        mode = forced_mode.upper() if forced_mode and forced_mode.upper() in ("VECTOR_PATH", "GRAPH_PATH", "HYBRID_FUSION") else intent

        vector_results = []
        graph_results = []

        # 1. Execute Vector Search (if needed)
        if mode in ("VECTOR_PATH", "HYBRID_FUSION"):
            vector_results = self.vector_store.search(query, top_k=limit * 2)

        # 2. Execute Graph Traversal (if needed)
        if mode in ("GRAPH_PATH", "HYBRID_FUSION"):
            # If specific entities found, traverse from them. Otherwise search by keyword.
            if entities:
                for eid in entities[:3]:
                    subgraph = self.semantic_engine.query_semantic(eid, limit=limit, include_relations=True)
                    graph_results.extend(subgraph)
            else:
                graph_results = self.semantic_engine.query_semantic(query, limit=limit * 2, include_relations=True)

        # Deduplicate graph results
        seen_gids = set()
        unique_graph = []
        for g in graph_results:
            if g["id"] not in seen_gids:
                seen_gids.add(g["id"])
                unique_graph.append(g)

        # 3. Reciprocal Rank Fusion (RRF)
        fused = self._reciprocal_rank_fusion(vector_results, unique_graph)

        return {
            "query": query,
            "classified_intent": intent,
            "executed_mode": mode,
            "detected_entities": entities,
            "total_matches": len(fused),
            "results": fused[:limit]
        }

    def _reciprocal_rank_fusion(
        self,
        vector_items: list[dict[str, Any]],
        graph_items: list[dict[str, Any]],
        k: int = 60
    ) -> list[dict[str, Any]]:
        scores: dict[str, float] = {}
        item_map: dict[str, dict[str, Any]] = {}

        # Process vector ranks
        for rank, item in enumerate(vector_items):
            item_id = item["id"]
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank + 1))
            item_map[item_id] = {
                "id": item_id,
                "title": item.get("metadata", {}).get("title", item_id),
                "type": item.get("namespace", "vector_match"),
                "summary": item.get("text", ""),
                "relations": [],
                "source": "vector_search"
            }

        # Process graph ranks
        for rank, item in enumerate(graph_items):
            item_id = item["id"]
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank + 1))
            if item_id in item_map:
                item_map[item_id]["relations"] = item.get("relations", [])
                item_map[item_id]["source"] = "hybrid_fused"
            else:
                item_map[item_id] = {
                    "id": item_id,
                    "title": item.get("title", item_id),
                    "type": item.get("entity_type", "semantic_node"),
                    "summary": str(item.get("properties", {})),
                    "relations": item.get("relations", []),
                    "source": "graph_traversal"
                }

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        final_results = []
        for item_id, rrf_score in sorted_items:
            data = item_map[item_id]
            data["rrf_score"] = round(rrf_score, 5)
            final_results.append(data)

        return final_results
