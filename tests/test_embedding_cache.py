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

    second = cache.embed_with_cache(provider, "voyage-3-large", ["aa", "bbb"])
    assert second == [[2.0], [3.0]]
    assert provider.calls == 1

    third = cache.embed_with_cache(provider, "voyage-3-large", ["aa", "cccc"])
    assert third == [[2.0], [4.0]]
    assert provider.calls == 2


def test_cache_keys_include_model(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.db")
    provider = CountingProvider()
    cache.embed_with_cache(provider, "model-a", ["x"])
    cache.embed_with_cache(provider, "model-b", ["x"])
    assert provider.calls == 2
