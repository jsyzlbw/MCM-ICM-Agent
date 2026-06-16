from __future__ import annotations

import hashlib
import math

import httpx


class FakeEmbeddingProvider:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]


class FakeRerankProvider:
    def rerank(self, query: str, documents: list[str], top_k: int) -> list[dict]:
        query_tokens = set(query.lower().split())
        scored = []
        for index, document in enumerate(documents):
            doc_tokens = set(document.lower().split())
            overlap = len(query_tokens & doc_tokens) / (len(query_tokens) or 1)
            scored.append({"index": index, "score": overlap})
        scored.sort(key=lambda row: row["score"], reverse=True)
        return scored[:top_k]


class VoyageEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "voyage-3-large",
        base_url: str = "https://api.voyageai.com/v1",
        timeout_seconds: int = 60,
        batch_size: int = 128,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = httpx.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"input": batch, "model": self.model},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            vectors.extend(item["embedding"] for item in response.json()["data"])
        return vectors


class VoyageRerankProvider:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "rerank-2",
        base_url: str = "https://api.voyageai.com/v1",
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def rerank(self, query: str, documents: list[str], top_k: int) -> list[dict]:
        if not documents:
            return []
        response = httpx.post(
            f"{self.base_url}/rerank",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"query": query, "documents": documents, "model": self.model, "top_k": top_k},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return [
            {"index": item["index"], "score": item["relevance_score"]}
            for item in response.json()["results"]
        ]
