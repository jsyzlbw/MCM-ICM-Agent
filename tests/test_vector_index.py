import chromadb

from mcm_agent.core.vector_index import VectorIndex


def test_vector_index_add_and_query_returns_nearest():
    index = VectorIndex(client=chromadb.EphemeralClient(), collection_name="test1")
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
    index = VectorIndex(client=chromadb.EphemeralClient(), collection_name="test2")
    index.add_chunks(ids=["c1"], embeddings=[[1.0, 0.0]], documents=["d"], metadatas=[{"title": "A"}])
    index.add_chunks(ids=["c1"], embeddings=[[1.0, 0.0]], documents=["d"], metadatas=[{"title": "A"}])
    hits = index.query([1.0, 0.0], top_n=5)
    assert len(hits) == 1
