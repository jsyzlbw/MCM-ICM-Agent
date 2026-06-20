from __future__ import annotations


def test_generate_stream_yields_text_chunks(monkeypatch) -> None:
    from mcm_agent.providers.llm import OpenAICompatibleLLMProvider

    chunks = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        "data: [DONE]",
    ]

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter(chunks)

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("mcm_agent.providers.llm.httpx.Client", _Client)
    provider = OpenAICompatibleLLMProvider(api_key="k", model="m", base_url="http://x/v1")

    assert "".join(provider.generate_stream("sys", "hi")) == "Hello world"
