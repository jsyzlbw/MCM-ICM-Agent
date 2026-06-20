import httpx
import pytest
import respx
from httpx import Response

from mcm_agent.providers.llm import AnthropicCompatibleLLMProvider

_URL = "https://api.deepseek.com/anthropic/v1/messages"


@respx.mock
def test_anthropic_provider_posts_messages_and_parses_text() -> None:
    route = respx.post(_URL).mock(
        return_value=Response(200, json={"content": [{"type": "text", "text": "hello"}], "id": "m1"})
    )
    provider = AnthropicCompatibleLLMProvider(
        api_key="k", model="deepseek-v4-flash", base_url="https://api.deepseek.com/anthropic"
    )

    result = provider.generate("sys", "prompt")

    assert result.content == "hello"
    assert route.called
    request = route.calls[0].request
    assert request.headers["x-api-key"] == "k"
    assert "anthropic-version" in request.headers


@respx.mock
def test_anthropic_provider_retries_then_raises_on_5xx() -> None:
    route = respx.post(_URL).mock(return_value=Response(503, text="busy"))
    provider = AnthropicCompatibleLLMProvider(
        api_key="k", model="m", base_url="https://api.deepseek.com/anthropic", max_retries=1
    )

    with pytest.raises(RuntimeError):
        provider.generate("sys", "prompt")
    assert route.call_count == 2


@respx.mock
def test_anthropic_provider_retries_transient_timeout() -> None:
    route = respx.post(_URL).mock(
        side_effect=[
            httpx.ReadTimeout("t"),
            Response(200, json={"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    provider = AnthropicCompatibleLLMProvider(
        api_key="k", model="m", base_url="https://api.deepseek.com/anthropic", max_retries=2
    )

    assert provider.generate("s", "p").content == "ok"
    assert route.call_count == 2
