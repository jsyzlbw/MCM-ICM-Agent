# RAG v2: Embeddings + Rerank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hybrid methodology retrieval — FTS ∪ vector candidates reordered by a reranker — with Voyage (embeddings + rerank) and chromadb, fully working offline via fake providers.

**Architecture:** New embedding/rerank providers (Voyage REST + deterministic fakes) join `ProviderBundle`. A content-hash SQLite cache avoids re-embedding. A chroma-backed `VectorIndex` stores per-workspace chunk vectors. `hybrid_search` fuses FTS + vector candidates and reranks. `MethodologyRAGAgent.run` gains **optional** `embedding_provider`/`reranker` — `None` preserves today's FTS-only behavior (existing tests stay green); when provided, it builds the vector index and uses `hybrid_search`.

**Tech Stack:** Python, httpx (Voyage REST), chromadb, sqlite3, pytest + respx (mock Voyage).

Implements `docs/superpowers/specs/2026-06-16-rag-v2-embeddings-design.md`.

---

## File Structure

- Create `src/mcm_agent/providers/embedding.py` — `FakeEmbeddingProvider`, `FakeRerankProvider`, `VoyageEmbeddingProvider`, `VoyageRerankProvider`.
- Create `src/mcm_agent/core/embedding_cache.py` — `EmbeddingCache` (content-hash SQLite).
- Create `src/mcm_agent/core/vector_index.py` — `VectorIndex` (chroma wrapper).
- Modify `src/mcm_agent/agents/rag.py` — `MethodologyHit.rerank_score`, `hybrid_search`, optional embedding/reranker in `MethodologyRAGAgent.run`.
- Modify `src/mcm_agent/providers/base.py` — `ProviderBundle.embedding`/`.reranker` (default `None`).
- Modify `src/mcm_agent/providers/factory.py` — build embedding/rerank from settings.
- Modify `src/mcm_agent/workflows/mvp.py` — demo bundle gets fakes; `methodology_rag` passes them.
- Modify `src/mcm_agent/config.py`, `src/mcm_agent/server/config_store.py`, `mcm_agent_config.example.json` — `embedding` config.
- Modify `pyproject.toml` (add chromadb), `.gitignore` (`.mcm_agent_cache/`).
- Tests: `tests/test_embedding_providers.py`, `tests/test_embedding_cache.py`, `tests/test_vector_index.py`, `tests/test_hybrid_search.py`, plus a hybrid test added to `tests/test_rag.py`.

---

## Task 1: Embedding + rerank providers

**Files:**
- Create: `src/mcm_agent/providers/embedding.py`
- Modify: `src/mcm_agent/providers/base.py`
- Test: `tests/test_embedding_providers.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_embedding_providers.py`:

```python
import httpx
import respx

from mcm_agent.providers.embedding import (
    FakeEmbeddingProvider,
    FakeRerankProvider,
    VoyageEmbeddingProvider,
    VoyageRerankProvider,
)


def test_fake_embedding_is_deterministic_normalized_fixed_dim():
    p = FakeEmbeddingProvider(dim=256)
    a = p.embed(["weighted topsis evaluation"])
    b = p.embed(["weighted topsis evaluation"])
    assert len(a) == 1 and len(a[0]) == 256
    assert a == b  # deterministic
    norm = sum(x * x for x in a[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-6  # normalized


def test_fake_rerank_orders_by_overlap_and_caps_top_k():
    r = FakeRerankProvider()
    out = r.rerank("figure design claim", ["figure design supports the claim", "unrelated text", "claim about figure"], top_k=2)
    assert len(out) == 2
    assert out[0]["index"] == 0  # highest overlap first
    assert out[0]["score"] >= out[1]["score"]


@respx.mock
def test_voyage_embedding_parses_response():
    respx.post("https://api.voyageai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]})
    )
    p = VoyageEmbeddingProvider(api_key="k", model="voyage-3-large")
    assert p.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


@respx.mock
def test_voyage_rerank_parses_response():
    respx.post("https://api.voyageai.com/v1/rerank").mock(
        return_value=httpx.Response(200, json={"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.4}]})
    )
    r = VoyageRerankProvider(api_key="k", model="rerank-2")
    out = r.rerank("q", ["d0", "d1"], top_k=2)
    assert out == [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.4}]
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_embedding_providers.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `src/mcm_agent/providers/embedding.py`:**

```python
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
```

Then add the two fields to `ProviderBundle` in `src/mcm_agent/providers/base.py` (defaults `None`, placed last so the dataclass stays valid):

```python
@dataclass(frozen=True)
class ProviderBundle:
    llm: TextGenerationProvider
    mineru: object
    search: object
    extractor: object
    official_data: object
    humanizer: object
    latex: object
    embedding: object | None = None
    reranker: object | None = None
```

- [ ] **Step 4: Run to verify it passes** — `python -m pytest tests/test_embedding_providers.py -v` → PASS (4).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/providers/embedding.py src/mcm_agent/providers/base.py tests/test_embedding_providers.py
git commit -m "feat: add Voyage + fake embedding/rerank providers"
```

---

## Task 2: Embedding cache

**Files:**
- Create: `src/mcm_agent/core/embedding_cache.py`
- Test: `tests/test_embedding_cache.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_embedding_cache.py`:

```python
from mcm_agent.core.embedding_cache import EmbeddingCache


class CountingProvider:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[float(len(t))] for t in texts]


def test_cache_embeds_only_misses(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.db")
    provider = CountingProvider()

    first = cache.embed_with_cache(provider, "voyage-3-large", ["aa", "bbb"])
    assert first == [[2.0], [3.0]]
    assert provider.calls == 1

    # second call: all cached -> provider not invoked again
    second = cache.embed_with_cache(provider, "voyage-3-large", ["aa", "bbb"])
    assert second == [[2.0], [3.0]]
    assert provider.calls == 1

    # a new text is a miss -> one more call, only for the miss
    third = cache.embed_with_cache(provider, "voyage-3-large", ["aa", "cccc"])
    assert third == [[2.0], [4.0]]
    assert provider.calls == 2


def test_cache_keys_include_model(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.db")
    provider = CountingProvider()
    cache.embed_with_cache(provider, "model-a", ["x"])
    cache.embed_with_cache(provider, "model-b", ["x"])
    assert provider.calls == 2  # different model -> separate entry
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_embedding_cache.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `src/mcm_agent/core/embedding_cache.py`:**

```python
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
```

- [ ] **Step 4: Run to verify it passes** — `python -m pytest tests/test_embedding_cache.py -v` → PASS (2).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/core/embedding_cache.py tests/test_embedding_cache.py
git commit -m "feat: add content-hash embedding cache"
```

---

## Task 3: Vector index (chromadb) + dependency

**Files:**
- Create: `src/mcm_agent/core/vector_index.py`
- Modify: `pyproject.toml`
- Test: `tests/test_vector_index.py`

- [ ] **Step 1: Install chromadb and add it to deps**

Run: `python -m pip install chromadb`
Expected: installs successfully (`python -c "import chromadb"` exits 0).
Then add `"chromadb>=0.5.0"` to the `dependencies` list in `pyproject.toml` (after `"python-multipart>=0.0.9"`).

If `pip install chromadb` fails in this environment, STOP and report BLOCKED with the error (the chosen vector-library route depends on it).

- [ ] **Step 2: Write the failing test** — create `tests/test_vector_index.py`:

```python
import chromadb

from mcm_agent.core.vector_index import VectorIndex


def test_vector_index_add_and_query_returns_nearest():
    index = VectorIndex(client=chromadb.EphemeralClient(), collection_name="t")
    index.add_chunks(
        ids=["c1", "c2"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        documents=["alpha doc", "beta doc"],
        metadatas=[{"title": "A"}, {"title": "B"}],
    )
    hits = index.query([0.9, 0.1], top_n=1)
    assert len(hits) == 1
    assert hits[0]["chunk_id"] == "c1"
    assert hits[0]["content"] == "alpha doc"
    assert hits[0]["metadata"]["title"] == "A"


def test_vector_index_upsert_is_idempotent():
    index = VectorIndex(client=chromadb.EphemeralClient(), collection_name="t")
    index.add_chunks(ids=["c1"], embeddings=[[1.0, 0.0]], documents=["d"], metadatas=[{"title": "A"}])
    index.add_chunks(ids=["c1"], embeddings=[[1.0, 0.0]], documents=["d"], metadatas=[{"title": "A"}])
    hits = index.query([1.0, 0.0], top_n=5)
    assert len(hits) == 1  # no duplicate
```

- [ ] **Step 3: Run to verify it fails** — `python -m pytest tests/test_vector_index.py -v` → FAIL (module missing).

- [ ] **Step 4: Implement `src/mcm_agent/core/vector_index.py`:**

```python
from __future__ import annotations

from pathlib import Path


class VectorIndex:
    def __init__(
        self,
        *,
        persist_dir: Path | None = None,
        collection_name: str = "methodology",
        client: object | None = None,
    ) -> None:
        import chromadb

        if client is not None:
            self._client = client
        elif persist_dir is not None:
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(persist_dir))
        else:
            self._client = chromadb.EphemeralClient()
        self._collection = self._client.get_or_create_collection(collection_name)

    def add_chunks(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(self, embedding: list[float], top_n: int) -> list[dict]:
        result = self._collection.query(query_embeddings=[embedding], n_results=top_n)
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits = []
        for index, chunk_id in enumerate(ids):
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "content": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                }
            )
        return hits
```

- [ ] **Step 5: Run to verify it passes** — `python -m pytest tests/test_vector_index.py -v` → PASS (2).

- [ ] **Step 6: Commit**

```bash
git add src/mcm_agent/core/vector_index.py pyproject.toml tests/test_vector_index.py
git commit -m "feat: add chroma-backed vector index"
```

---

## Task 4: Hybrid search

**Files:**
- Modify: `src/mcm_agent/agents/rag.py` (add `rerank_score` to `MethodologyHit`; add `hybrid_search`)
- Test: `tests/test_hybrid_search.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_hybrid_search.py`:

```python
import chromadb

from mcm_agent.agents.rag import MethodologyStore, hybrid_search
from mcm_agent.core.vector_index import VectorIndex
from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider


def _store(tmp_path):
    store = MethodologyStore(tmp_path / "rag.db")
    store.initialize()
    store.add_document("s", "Figure", "figure design supports the validation claim", relative_path="figure.md", chunk_id="figure.md#chunk-001")
    store.add_document("s", "Model", "model formulation defines variables", relative_path="model.md", chunk_id="model.md#chunk-001")
    return store


def test_hybrid_search_returns_reranked_top_k(tmp_path):
    store = _store(tmp_path)
    embedder = FakeEmbeddingProvider(dim=64)
    index = VectorIndex(client=chromadb.EphemeralClient(), collection_name="t")
    index.add_chunks(
        ids=["figure.md#chunk-001", "model.md#chunk-001"],
        embeddings=embedder.embed(["figure design supports the validation claim", "model formulation defines variables"]),
        documents=["figure design supports the validation claim", "model formulation defines variables"],
        metadatas=[{"title": "Figure", "relative_path": "figure.md", "source_type": "method_note"}, {"title": "Model", "relative_path": "model.md", "source_type": "method_note"}],
    )

    hits = hybrid_search(store, index, embedder, FakeRerankProvider(), "figure design claim", top_k=1)

    assert len(hits) == 1
    assert hits[0].title == "Figure"
    assert hits[0].rerank_score > 0
    assert hits[0].query == "figure design claim"


def test_hybrid_search_without_reranker_returns_fts_candidates(tmp_path):
    store = _store(tmp_path)
    hits = hybrid_search(store, None, None, None, "model formulation", top_k=3)
    assert any(h.title == "Model" for h in hits)
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_hybrid_search.py -v` → FAIL (`hybrid_search` undefined).

- [ ] **Step 3: Add `rerank_score` to `MethodologyHit` and implement `hybrid_search` in `src/mcm_agent/agents/rag.py`.**

In the `MethodologyHit` class add one field (after `page_hint`):

```python
    rerank_score: float = 0.0
```

Add this function at module level (e.g., after `search_methodology_queries`):

```python
def hybrid_search(
    store: MethodologyStore,
    vector_index: object | None,
    embedding_provider: object | None,
    reranker: object | None,
    query: str,
    *,
    fts_n: int = 10,
    vec_n: int = 10,
    top_k: int = 3,
) -> list[MethodologyHit]:
    candidates: dict[str, MethodologyHit] = {}
    for hit in store.search(query, limit=fts_n):
        key = hit.chunk_id or hit.relative_path or hit.title
        candidates[key] = hit

    if embedding_provider is not None and vector_index is not None:
        query_vector = embedding_provider.embed([query])[0]
        for item in vector_index.query(query_vector, vec_n):
            key = item["chunk_id"]
            if key in candidates:
                continue
            meta = item.get("metadata") or {}
            candidates[key] = MethodologyHit(
                source=str(meta.get("source", meta.get("relative_path", key))),
                title=str(meta.get("title", key)),
                content=item.get("content", ""),
                rank=0,
                source_type=str(meta.get("source_type", "method_note")),
                relative_path=str(meta.get("relative_path", "")),
                chunk_id=key,
                chunk_index=int(meta.get("chunk_index", 1)),
                page_hint=str(meta.get("page_hint", "")),
            )

    candidate_list = list(candidates.values())
    if not candidate_list:
        return []

    if reranker is not None:
        ranked = reranker.rerank(query, [c.content for c in candidate_list], top_k)
        ordered: list[MethodologyHit] = []
        for position, row in enumerate(ranked, 1):
            base = candidate_list[row["index"]]
            ordered.append(
                base.model_copy(update={"rerank_score": float(row["score"]), "rank": position, "query": query})
            )
        return ordered

    return [
        candidate.model_copy(update={"rank": position, "query": query})
        for position, candidate in enumerate(candidate_list[:top_k], 1)
    ]
```

- [ ] **Step 4: Run to verify it passes** — `python -m pytest tests/test_hybrid_search.py -v` → PASS (2).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/agents/rag.py tests/test_hybrid_search.py
git commit -m "feat: add hybrid FTS+vector rerank search"
```

---

## Task 5: Wire into RAG agent, config, factory, workflow

**Files:**
- Modify: `src/mcm_agent/agents/rag.py` (`MethodologyRAGAgent.run`)
- Modify: `src/mcm_agent/config.py`, `src/mcm_agent/server/config_store.py`, `mcm_agent_config.example.json`
- Modify: `src/mcm_agent/providers/factory.py`, `src/mcm_agent/workflows/mvp.py`
- Modify: `.gitignore`
- Test: add one hybrid test to `tests/test_rag.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_rag.py`:

```python
def test_methodology_rag_agent_builds_vector_index_and_reranks(tmp_path: Path) -> None:
    import chromadb

    from mcm_agent.core.vector_index import VectorIndex
    from mcm_agent.providers.embedding import FakeEmbeddingProvider, FakeRerankProvider

    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "notes.md").write_text(
        "Figure design should support the validation claim. "
        "Model formulation should define variables and constraints.",
        encoding="utf-8",
    )

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
        embedding_provider=FakeEmbeddingProvider(dim=64),
        reranker=FakeRerankProvider(),
        vector_index=VectorIndex(client=chromadb.EphemeralClient(), collection_name="run_001"),
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    assert hits
    assert any("rerank_score" in hit for hit in hits)
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_rag.py::test_methodology_rag_agent_builds_vector_index_and_reranks -v` → FAIL (`run()` has no `embedding_provider`).

- [ ] **Step 3: Update `MethodologyRAGAgent.run` in `src/mcm_agent/agents/rag.py`.** Replace the method signature and the retrieval/ingest section so it accepts optional embedding/reranker/vector_index and builds the vector index during ingest, then uses `hybrid_search` when an embedding provider is present. Replace the existing `run` method with:

```python
    def run(
        self,
        workspace_root: Path,
        supervisor_skills_dir: Path | None,
        knowledge_base_dir: Path | None = None,
        ingest_extensions: list[str] | None = None,
        mineru_provider: object | None = None,
        embedding_provider: object | None = None,
        reranker: object | None = None,
        vector_index: object | None = None,
        embedding_cache: object | None = None,
        embedding_model: str = "voyage-3-large",
    ) -> None:
        rag_dir = workspace_root / "rag"
        checklist_dir = rag_dir / "review_checklists"
        checklist_dir.mkdir(parents=True, exist_ok=True)
        store = MethodologyStore(rag_dir / "methodology.db")
        store.initialize()

        warnings: list[str] = []
        if supervisor_skills_dir is not None:
            warnings = import_supervisor_skills(supervisor_skills_dir, store)
        if knowledge_base_dir is not None:
            warnings.extend(
                ingest_knowledge_base(
                    knowledge_base_dir,
                    store,
                    ingest_extensions,
                    mineru_provider=mineru_provider,
                    parsed_knowledge_dir=rag_dir / "parsed_knowledge",
                )
            )

        index = vector_index
        if embedding_provider is not None and index is None:
            from mcm_agent.core.vector_index import VectorIndex

            index = VectorIndex(persist_dir=rag_dir / "chroma", collection_name="methodology")
        if embedding_provider is not None and index is not None:
            warnings.extend(
                _index_store_vectors(store, index, embedding_provider, embedding_cache, embedding_model)
            )

        if embedding_provider is not None and reranker is not None and index is not None:
            hits: list[MethodologyHit] = []
            for query in PAPER_QUALITY_QUERIES:
                hits.extend(hybrid_search(store, index, embedding_provider, reranker, query))
        else:
            hits = search_methodology_queries(store, PAPER_QUALITY_QUERIES)
        write_json(rag_dir / "methodology_hits.json", [hit.model_dump() for hit in hits])

        notes = ["# RAG Retrieval Notes", ""]
        notes.extend(f"- {warning}" for warning in warnings)
        (rag_dir / "retrieval_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")

        _write_default_checklists(checklist_dir)
```

Add two module-level helpers in `rag.py` (near the other functions). `_index_store_vectors` reads all chunks out of the FTS store and adds their vectors to the index; `_write_default_checklists` holds the three checklist writes moved verbatim out of `run`:

```python
def _index_store_vectors(
    store: MethodologyStore,
    vector_index: object,
    embedding_provider: object,
    embedding_cache: object | None,
    embedding_model: str,
) -> list[str]:
    import sqlite3

    rows: list[tuple] = []
    with sqlite3.connect(store.db_path) as conn:
        rows = conn.execute(
            "SELECT source, title, content, source_type, relative_path, page_hint, chunk_id, chunk_index "
            "FROM methodology_docs"
        ).fetchall()
    if not rows:
        return []
    ids, documents, metadatas, texts = [], [], [], []
    for row in rows:
        source, title, content, source_type, relative_path, page_hint, chunk_id, chunk_index = row
        cid = chunk_id or f"{relative_path or title}#chunk-001"
        ids.append(cid)
        documents.append(content)
        texts.append(content)
        metadatas.append(
            {
                "source": source or "",
                "title": title or "",
                "source_type": source_type or "method_note",
                "relative_path": relative_path or "",
                "page_hint": page_hint or "",
                "chunk_index": int(chunk_index) if str(chunk_index).isdigit() else 1,
            }
        )
    try:
        if embedding_cache is not None:
            embeddings = embedding_cache.embed_with_cache(embedding_provider, embedding_model, texts)
        else:
            embeddings = embedding_provider.embed(texts)
        vector_index.add_chunks(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        return []
    except Exception as exc:  # noqa: BLE001 - methodology RAG is non-critical guidance
        return [f"Vector indexing degraded to FTS-only: {exc}"]


def _write_default_checklists(checklist_dir: Path) -> None:
    (checklist_dir / "modeling_checklist.md").write_text(
        "\n".join(["# Modeling Checklist", "", "- Check problem fit.", "- Check data feasibility.", "- Check implementation risk.", ""]),
        encoding="utf-8",
    )
    (checklist_dir / "figure_checklist.md").write_text(
        "\n".join(["# Figure Checklist", "", "- Every data figure must have a data source.", "- Every concept figure must be vector-first.", "- Every result figure must support a paper claim.", ""]),
        encoding="utf-8",
    )
    (checklist_dir / "pre_submission_checklist.md").write_text(
        "\n".join(["# Pre Submission Checklist", "", "- Check macro logic.", "- Check writing details.", "- Check English expression.", "- Check LaTeX formatting.", "- Check figure quality.", ""]),
        encoding="utf-8",
    )
```

> Note: the FTS-only branch (when no embedding provider) calls the unchanged `search_methodology_queries`, so the 11 existing `test_rag.py` tests keep their current behavior and assertions.

- [ ] **Step 4: Add config support.**

In `src/mcm_agent/config.py`, add fields to `Settings` (after the `rag_*` fields):

```python
    embedding_provider: str = "fake"
    voyage_api_key: str = ""
    embedding_base_url: str = "https://api.voyageai.com/v1"
    embedding_model: str = "voyage-3-large"
    rerank_model: str = "rerank-2"
```

And add to the `mapping` dict in `_settings_overrides_from_json`:

```python
        ("embedding", "provider"): "embedding_provider",
        ("embedding", "api_key"): "voyage_api_key",
        ("embedding", "base_url"): "embedding_base_url",
        ("embedding", "embedding_model"): "embedding_model",
        ("embedding", "rerank_model"): "rerank_model",
```

In `src/mcm_agent/server/config_store.py`, add an `embedding` block to `default_config()` (after the `rag` block):

```python
        "embedding": {
            "provider": "voyage",
            "api_key": "",
            "base_url": "https://api.voyageai.com/v1",
            "embedding_model": "voyage-3-large",
            "rerank_model": "rerank-2",
        },
```

Add the same block to `mcm_agent_config.example.json` (after the `rag` object).

- [ ] **Step 5: Build providers in the factory and pass them in the workflow.**

In `src/mcm_agent/providers/factory.py`, add the import and construction, then include them in the returned `ProviderBundle`:

```python
from mcm_agent.providers.embedding import (
    FakeEmbeddingProvider,
    FakeRerankProvider,
    VoyageEmbeddingProvider,
    VoyageRerankProvider,
)
```

```python
    if settings.embedding_provider == "voyage" and settings.voyage_api_key:
        embedding = VoyageEmbeddingProvider(
            settings.voyage_api_key,
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            timeout_seconds=settings.mcm_agent_http_timeout_seconds,
        )
        reranker = VoyageRerankProvider(
            settings.voyage_api_key,
            model=settings.rerank_model,
            base_url=settings.embedding_base_url,
            timeout_seconds=settings.mcm_agent_http_timeout_seconds,
        )
    else:
        embedding = FakeEmbeddingProvider()
        reranker = FakeRerankProvider()
```

Add `embedding=embedding, reranker=reranker` to the `ProviderBundle(...)` return.

In `src/mcm_agent/workflows/mvp.py`: (a) in `_default_demo_providers`, import and pass `FakeEmbeddingProvider()`/`FakeRerankProvider()` as `embedding=`/`reranker=`; (b) in the `methodology_rag` handler, pass them plus a cache through to the agent:

```python
    def methodology_rag(workspace_root: Path) -> list[str]:
        knowledge_base_dir = Path(settings.rag_knowledge_base_dir)
        if not knowledge_base_dir.is_absolute():
            knowledge_base_dir = Path.cwd() / knowledge_base_dir
        from mcm_agent.core.embedding_cache import EmbeddingCache

        MethodologyRAGAgent().run(
            workspace_root,
            supervisor_skills_dir,
            knowledge_base_dir=knowledge_base_dir,
            ingest_extensions=settings.rag_ingest_extensions,
            mineru_provider=provider_bundle.mineru,
            embedding_provider=provider_bundle.embedding,
            reranker=provider_bundle.reranker,
            embedding_cache=EmbeddingCache(Path(".mcm_agent_cache") / "embeddings.db"),
            embedding_model=settings.embedding_model,
        )
        return ["rag/methodology_hits.json", "review/methodology_checklist_report.md"]
```

Add `FakeEmbeddingProvider`/`FakeRerankProvider` to the imports at the top of `mvp.py` (from `mcm_agent.providers.embedding`).

- [ ] **Step 6: Ignore the cache dir.** Append to `.gitignore`:

```
# Embedding cache
.mcm_agent_cache/
```

- [ ] **Step 7: Run the RAG + workflow + config tests**

Run: `python -m pytest tests/test_rag.py tests/test_mvp_workflow.py tests/test_server_config.py -v`
Expected: PASS. (Existing `test_rag.py` tests use the FTS-only branch and are unchanged; the new hybrid test passes; the full demo workflow now builds a chroma index with fake vectors and still completes.)

If any existing `test_rag.py` assertion now fails because hybrid reordering changed hit order, that means a test accidentally exercised the hybrid branch — confirm those tests pass NO embedding provider (FTS-only) and fix the test setup, not the assertions.

- [ ] **Step 8: Commit**

```bash
git add src/mcm_agent/agents/rag.py src/mcm_agent/config.py src/mcm_agent/server/config_store.py mcm_agent_config.example.json src/mcm_agent/providers/factory.py src/mcm_agent/workflows/mvp.py .gitignore tests/test_rag.py
git commit -m "feat: wire hybrid RAG (embeddings+rerank) into agent, config, workflow"
```

---

## Task 6: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Full suite** — Run: `python -m pytest -q` → expect all pass (299 prior + new). Investigate any failure; do not weaken assertions.
- [ ] **Step 2: Lint** — Run: `ruff check src tests` → expect clean; fix issues in new files.
- [ ] **Step 3: Live offline smoke** — `mcm-agent gui`, create a workspace, upload a problem, run a demo to `methodology_rag`, confirm `rag/methodology_hits.json` exists and entries carry `rerank_score` (fake path). Kill the server.
- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint fixes for rag v2"
```

---

## Self-Review notes (spec coverage)

- §3.1 providers (Voyage+fake embedding/rerank) → Task 1.
- §3.2 content-hash cache → Task 2.
- §3.3 chroma VectorIndex → Task 3.
- §3.4 hybrid_search (FTS∪vector→rerank) → Task 4; wired into agent → Task 5.
- §4 config (`embedding` section, Settings, mapping, example.json, default_config) → Task 5 Step 4.
- §5 degradation: no key→fake (factory Task 5 Step 5); embedding failure→FTS-only note (`_index_store_vectors` try/except Task 5 Step 3); cost cache (Task 2 + wired Task 5 Step 5).
- §6 error handling → `_index_store_vectors` degradation + cache model-keyed.
- §7 testing → Tasks 1-5 tests + Task 6 full suite; respx mocks Voyage; chroma ephemeral; no real key.
- §8 file changes → all tasks; §9 chromadb dep → Task 3 Step 1.

**Backward-compat guard:** `MethodologyRAGAgent.run` keeps an FTS-only branch when `embedding_provider is None`, so existing `test_rag.py` (11 tests) stays green; the demo bundle passes fakes so the workflow exercises the hybrid path.

**Risk:** chromadb install weight/compat (Task 3 Step 1 is the gate — BLOCK if it fails). chroma in the demo-workflow test path adds runtime; if `test_mvp_workflow` becomes slow/flaky, consider passing `vector_index` only when a knowledge base is non-empty (optimization, not required).
