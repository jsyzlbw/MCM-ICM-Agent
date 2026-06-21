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
    assert a == b
    norm = sum(x * x for x in a[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_fake_rerank_orders_by_overlap_and_caps_top_k():
    r = FakeRerankProvider()
    out = r.rerank("figure design claim", ["figure design supports the claim", "unrelated text", "claim about figure"], top_k=2)
    assert len(out) == 2
    assert out[0]["index"] == 0
    assert out[0]["score"] >= out[1]["score"]


@respx.mock
def test_voyage_embedding_parses_response():
    respx.post("https://api.voyageai.com/v1/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]})
    )
    p = VoyageEmbeddingProvider(api_key="k", model="voyage-3-large")
    assert p.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


@respx.mock
def test_voyage_embedding_retries_on_429(monkeypatch):
    # No real sleeping in tests.
    monkeypatch.setattr("mcm_agent.providers.embedding.time.sleep", lambda _s: None)
    route = respx.post("https://api.voyageai.com/v1/embeddings")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "1"}),
        httpx.Response(200, json={"data": [{"embedding": [0.5, 0.6]}]}),
    ]
    p = VoyageEmbeddingProvider(api_key="k", model="voyage-3-large", batch_size=16)
    assert p.embed(["only one"]) == [[0.5, 0.6]]
    assert route.call_count == 2  # first 429, then success


@respx.mock
def test_voyage_embedding_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr("mcm_agent.providers.embedding.time.sleep", lambda _s: None)
    route = respx.post("https://api.voyageai.com/v1/embeddings")
    route.side_effect = [
        httpx.ConnectError("SSL: UNEXPECTED_EOF_WHILE_READING"),  # network drop (e.g. laptop sleep)
        httpx.Response(200, json={"data": [{"embedding": [0.7, 0.8]}]}),
    ]
    p = VoyageEmbeddingProvider(api_key="k", model="voyage-3-large", batch_size=16)
    assert p.embed(["only one"]) == [[0.7, 0.8]]
    assert route.call_count == 2  # transient ConnectError then success


@respx.mock
def test_voyage_rerank_parses_response():
    # Voyage's real /rerank returns results under "data" (verified against the live API),
    # not "results" (that was a Cohere-ism that silently broke real reranking).
    respx.post("https://api.voyageai.com/v1/rerank").mock(
        return_value=httpx.Response(200, json={"data": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.4}]})
    )
    r = VoyageRerankProvider(api_key="k", model="rerank-2")
    out = r.rerank("q", ["d0", "d1"], top_k=2)
    assert out == [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.4}]
