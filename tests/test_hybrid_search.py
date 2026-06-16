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
    index = VectorIndex(client=chromadb.EphemeralClient(), collection_name="hybridtest")
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
