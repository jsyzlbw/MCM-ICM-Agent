from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


class EmbeddingCache:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (hash TEXT PRIMARY KEY, vector TEXT NOT NULL)"
            )

    def embed_with_cache(self, provider: object, model: str, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        misses: list[str] = []
        miss_indexes: list[int] = []
        for index, text in enumerate(texts):
            cached = self._get(model, text)
            if cached is not None:
                results[index] = cached
            else:
                misses.append(text)
                miss_indexes.append(index)
        if misses:
            embedded = provider.embed(misses)
            for index, vector in zip(miss_indexes, embedded):
                results[index] = list(vector)
                self._put(model, texts[index], list(vector))
        return [vector if vector is not None else [] for vector in results]

    def _key(self, model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\n{text}".encode("utf-8")).hexdigest()

    def _get(self, model: str, text: str) -> list[float] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT vector FROM embeddings WHERE hash = ?", (self._key(model, text),)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _put(self, model: str, text: str, vector: list[float]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (hash, vector) VALUES (?, ?)",
                (self._key(model, text), json.dumps(vector)),
            )
