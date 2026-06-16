# RAG v2: Embeddings + Rerank (Voyage + chromadb) Design

Status date: 2026-06-16
Status: design approved in brainstorming; pending user review of this spec.

## 1. Goal

Upgrade methodology retrieval from keyword-only (SQLite FTS5) to **hybrid retrieval**: keyword (FTS) + semantic (vector) candidates, fused and reordered by a cross-encoder reranker. This improves which methodology chunks reach the paper-quality stages. The RAG corpus stays the user's `knowledge_base/` (flat files) ingested per-workspace during `methodology_rag`; v2 adds an embedding+vector+rerank layer on top, with full offline behavior via fake providers.

## 2. Decisions (from brainstorming)

| Decision | Choice |
| --- | --- |
| Retrieval architecture | **Hybrid**: FTS top-N ∪ vector top-N → Voyage rerank → top-K |
| Vector store | **chromadb** (per-workspace persistent collection) |
| Embedding/rerank provider | **Voyage** (`voyage-3-large`, `rerank-2`) via httpx REST; fake fallback |
| Offline / no-key | **fake embedding + fake rerank** run the full vector+rerank path (deterministic) |
| Cost control | **content-hash embedding cache** (global, reused across runs) |

## 3. Architecture

### 3.1 Providers (`src/mcm_agent/providers/embedding.py`)

Two small provider interfaces + Voyage + fake implementations, added to `ProviderBundle`:

- `EmbeddingProvider.embed(texts: list[str]) -> list[list[float]]`
  - `VoyageEmbeddingProvider`: `POST {base_url}/embeddings` `{input: texts, model}` with `Authorization: Bearer <key>`; returns `data[].embedding`. Batches (e.g. ≤128 inputs/call).
  - `FakeEmbeddingProvider`: deterministic vector per text — tokenize, hash each token into a fixed `dim` (default 256) accumulator, L2-normalize. Same text → same vector; no network.
- `RerankProvider.rerank(query: str, documents: list[str], top_k: int) -> list[RerankResult]` where `RerankResult = {index, score}`.
  - `VoyageRerankProvider`: `POST {base_url}/rerank` `{query, documents, model, top_k}`; returns `results[].{index, relevance_score}`.
  - `FakeRerankProvider`: deterministic score = lexical token-overlap ratio of query vs document; stable sort desc.

Selection: `provider == "voyage"` and non-empty `api_key` → Voyage; otherwise fake. Mirrors the existing LLM/humanizer/MinerU fake pattern.

### 3.2 Embedding cache (`src/mcm_agent/core/embedding_cache.py`)

Global SQLite cache so identical chunks are embedded once across runs/workspaces.

- Table `embeddings(hash TEXT PRIMARY KEY, model TEXT, dim INTEGER, vector BLOB)`; `hash = sha256(f"{model}\n{text}")`; vector stored as `numpy.float32` bytes.
- `EmbeddingCache.embed_with_cache(provider, model, texts) -> list[vector]`: look up each text; embed only misses (one batched provider call for misses); store; return in input order.
- Default path `.mcm_agent_cache/embeddings.db` (cwd-relative); gitignored. Configurable later if needed.

### 3.3 Vector store (chromadb)

- Per-workspace persistent collection at `workspace/rag/chroma/` (collection name `methodology`).
- During ingestion, for every chunk already added to the FTS store, also add to chroma: `ids=[chunk_id]`, `embeddings=[vector]` (we always pass our own vectors — chroma never calls an embedding backend), `documents=[content]`, `metadatas=[{source, title, source_type, relative_path, page_hint, chunk_index}]`.
- Wrapped in a thin `VectorIndex` class (`add_chunks(...)`, `query(vector, top_n) -> list[chunk_id+metadata+content]`) so chroma stays isolated behind one interface and tests can swap an ephemeral client.

### 3.4 Hybrid retrieval

New `hybrid_search(store, vector_index, embedding_provider, reranker, query, *, fts_n=10, vec_n=10, top_k=3) -> list[MethodologyHit]`:
1. `fts = store.search(query, limit=fts_n)` (existing FTS).
2. `qvec = embedding_provider.embed([query])[0]`; `vec = vector_index.query(qvec, vec_n)`.
3. Merge candidates, dedup by `chunk_id` (keep richest metadata).
4. `ranked = reranker.rerank(query, [c.content for c in candidates], top_k)`; reorder candidates by `ranked`, take `top_k`; attach `rerank_score`.
5. Return `MethodologyHit[]` (existing model + a `rerank_score: float = 0.0` field added).

`MethodologyRAGAgent.run` builds the FTS store + vector index during ingestion, then runs `hybrid_search` for each `PAPER_QUALITY_QUERIES` entry and writes the (now rerank-ordered) `rag/methodology_hits.json`.

## 4. Configuration

New `embedding` section (committed to `mcm_agent_config.example.json` and `config_store.default_config()`):

```json
"embedding": {
  "provider": "voyage",
  "api_key": "",
  "base_url": "https://api.voyageai.com/v1",
  "embedding_model": "voyage-3-large",
  "rerank_model": "rerank-2"
}
```

`Settings` gains: `embedding_provider="fake"`, `voyage_api_key=""`, `embedding_base_url="https://api.voyageai.com/v1"`, `embedding_model="voyage-3-large"`, `rerank_model="rerank-2"`. Add the nested→flat mapping entries in `config.py._settings_overrides_from_json`. `api_key` is masked by the existing `mask_config` (ends with `_api_key`? no — key is `api_key`, already masked). The GUI Settings screen picks the new section up automatically; a per-provider "test connection" for `embedding` in provider-smoke is a follow-up (the field still saves/masks normally in this phase).

Default `provider` in the example is `voyage`, but with an empty key the runtime resolves to **fake**, so demos/tests stay offline.

## 5. Degradation & cost

- **No key / provider=fake** → fake embedding + fake rerank; full hybrid path runs deterministically offline.
- **Voyage embedding failure** (network/quota) during ingest → log a note in `rag/retrieval_notes.md`, fall back to fake embeddings for the failed batch so the workspace still builds (methodology RAG is non-critical guidance, must not crash the run).
- **Voyage rerank failure** → keep the merged FTS∪vector order (no reorder) + note.
- **chroma unavailable** → degrade to FTS-only + note.
- **Cost**: content-hash cache means a static `knowledge_base/` is embedded once; subsequent runs reuse vectors. Rerank is per-query at retrieval time (cheap, top_k small).

## 6. Error handling

- Malformed/empty knowledge base → unchanged (empty is valid; no chunks → empty collection → FTS-only effectively).
- Voyage HTTP errors caught per batch/call; surfaced as notes, never secrets.
- Embedding dim mismatch between a cached vector (old model) and current model → cache key includes model, so different models never collide.
- chroma persist dir collisions across runs → collection rebuilt/upserted by `chunk_id` (idempotent add via upsert).

## 7. Testing

All offline, deterministic, no real key (mirrors existing `tests/test_rag.py`):

- `tests/test_embedding_providers.py`: `FakeEmbeddingProvider` deterministic + normalized + fixed dim; `FakeRerankProvider` orders by overlap; Voyage providers parse a mocked httpx response (respx) without a real key.
- `tests/test_embedding_cache.py`: second call with same (model,text) does **not** re-invoke the provider (assert call count); different model → separate entry.
- `tests/test_vector_index.py`: add chunks + query returns nearest by our vectors (use `chromadb.EphemeralClient`).
- `tests/test_hybrid_search.py`: with fakes, hybrid returns rerank-ordered top-K; dedups FTS∪vector; rerank-failure path keeps order.
- Update `tests/test_rag.py`: `MethodologyRAGAgent` with fake embedding/rerank builds the chroma collection and writes rerank-ordered `methodology_hits.json`; empty KB still valid. (Verify existing FTS assertions still hold or adjust to hybrid output.)
- No real Voyage key in any test; chroma uses ephemeral/temp dirs.

## 8. File-level changes

New:
```
src/mcm_agent/providers/embedding.py        # Voyage + fake embedding & rerank providers
src/mcm_agent/core/embedding_cache.py        # content-hash SQLite cache
src/mcm_agent/core/vector_index.py           # chroma wrapper (VectorIndex)
tests/test_embedding_providers.py
tests/test_embedding_cache.py
tests/test_vector_index.py
tests/test_hybrid_search.py
```
Modified:
```
src/mcm_agent/agents/rag.py                  # hybrid_search + build vector index in MethodologyRAGAgent.run; MethodologyHit.rerank_score
src/mcm_agent/providers/base.py              # ProviderBundle gains embedding + reranker
src/mcm_agent/providers/factory.py           # build embedding/rerank providers from settings
src/mcm_agent/workflows/mvp.py               # methodology_rag handler passes embedding/reranker
src/mcm_agent/config.py                       # Settings fields + JSON mapping for `embedding`
src/mcm_agent/server/config_store.py          # default_config() gains `embedding`
mcm_agent_config.example.json                 # `embedding` section
pyproject.toml                                # add chromadb dependency
.gitignore                                    # ignore .mcm_agent_cache/
docs/PROJECT_STATUS.md                        # note RAG v2 (optional)
```

## 9. Dependencies

- Add **chromadb** to `pyproject.toml` dependencies. (Heavier than numpy brute-force, but the chosen vector-library route; pin a recent version.)
- Voyage via existing `httpx` (no new SDK). `respx` (already a dev dep) mocks Voyage in tests.

## 10. Scope / non-goals / follow-ups

In scope: embedding+rerank providers (+fakes), cache, chroma index, hybrid retrieval, RAG-agent wiring, config, tests.

Non-goals (future): chunk-level re-embedding on partial edits beyond content-hash; cross-encoder alternatives; embedding the per-run search/extraction corpus (this is methodology-RAG only); GUI surfacing of rerank scores; tuning fts_n/vec_n/top_k.

Open implementation note: keep existing `tests/test_rag.py` green — if hybrid reordering changes asserted hit order, update those assertions to reflect rerank output (document the change in the commit).
