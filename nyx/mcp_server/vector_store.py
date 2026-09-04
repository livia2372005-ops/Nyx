import math
import re
import json
import sqlite3
import struct
from pathlib import Path
from typing import Any
from .db import get_connection

class LocalVectorStore:
    """
    Lightweight, local-first vector store using dense subword/character n-gram TF-IDF embeddings
    and exact cosine similarity.
    Runs 100% offline, zero-latency, zero external API keys.
    """
    def __init__(self, db_path: Path | str | None = None, dimension: int = 256):
        self.db_path = db_path
        self.dim = dimension
        self._init_vector_table()

    def _init_vector_table(self):
        conn = get_connection(self.db_path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_embeddings (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,  -- 'episodic' or 'semantic'
                    text_content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata TEXT DEFAULT '{}'
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vec_ns ON vector_embeddings(namespace);")
        conn.close()

    def _compute_embedding(self, text: str) -> list[float]:
        """
        Computes a normalized dense vector embedding using feature hashing on words and character 3-grams.
        This captures both exact words and semantic/morphological similarities locally.
        """
        clean_text = text.lower().strip()
        tokens = re.findall(r"\b\w+\b", clean_text)
        vec = [0.0] * self.dim

        if not tokens and not clean_text:
            return vec

        # 1. Word hashing with position weighting
        for idx, token in enumerate(tokens):
            h = hash(token) % self.dim
            weight = 1.0 + (1.0 / (1.0 + idx * 0.1))
            vec[h] += weight

        # 2. Character 3-gram hashing for subword/typo/conceptual similarity
        for i in range(len(clean_text) - 2):
            trigram = clean_text[i:i+3]
            h = hash(trigram) % self.dim
            vec[h] += 0.5

        # Normalize vector to unit length (L2 norm)
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def _pack_vector(self, vec: list[float]) -> bytes:
        return struct.pack(f"{len(vec)}f", *vec)

    def _unpack_vector(self, blob: bytes) -> list[float]:
        num_floats = len(blob) // 4
        return list(struct.unpack(f"{num_floats}f", blob))

    def upsert(self, doc_id: str, namespace: str, text: str, metadata: dict[str, Any] | None = None):
        """Indexes or updates text content and its vector embedding."""
        vec = self._compute_embedding(text)
        packed = self._pack_vector(vec)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        conn = get_connection(self.db_path)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO vector_embeddings (id, namespace, text_content, embedding, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (doc_id, namespace, text, packed, meta_json))
        conn.close()

    def search(self, query: str, namespace: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Searches documents by cosine similarity against query vector.
        """
        q_vec = self._compute_embedding(query)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        if namespace:
            cursor.execute("SELECT id, namespace, text_content, embedding, metadata FROM vector_embeddings WHERE namespace = ?", (namespace,))
        else:
            cursor.execute("SELECT id, namespace, text_content, embedding, metadata FROM vector_embeddings")

        rows = cursor.fetchall()
        conn.close()

        scored = []
        for r in rows:
            doc_vec = self._unpack_vector(r["embedding"])
            # Cosine similarity between two unit vectors is dot product
            dot = sum(a * b for a, b in zip(q_vec, doc_vec))
            if dot > 0.05:  # threshold
                try:
                    meta = json.loads(r["metadata"])
                except Exception:
                    meta = {}
                scored.append({
                    "id": r["id"],
                    "namespace": r["namespace"],
                    "text": r["text_content"],
                    "score": round(dot, 4),
                    "metadata": meta
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]
