import httpx
import pytest
import respx
from httpx import Response

from mcm_agent.providers.llm import OpenAICompatibleLLMProvider

_URL = "https://api.example.com/v1/chat/completions"


@respx.mock
def test_llm_retries_transient_timeout_then_succeeds() -> None:
    route = respx.post(_URL).mock(
        side_effect=[
            httpx.ReadTimeout("timed out"),
            Response(200, json={"choices": [{"message": {"content": "ok"}}], "id": "x"}),
        ]
    )
    provider = OpenAICompatibleLLMProvider(
        api_key="k", model="m", base_url="https://api.example.com/v1", max_retries=2
    )

    result = provider.generate("sys", "prompt")

    assert result.content == "ok"
    assert route.call_count == 2


@respx.mock
def test_llm_retries_on_5xx_then_raises_after_attempts() -> None:
    route = respx.post(_URL).mock(return_value=Response(503, text="busy"))
    provider = OpenAICompatibleLLMProvider(
        api_key="k", model="m", base_url="https://api.example.com/v1", max_retries=1
    )

    with pytest.raises(RuntimeError):
        provider.generate("sys", "prompt")
    assert route.call_count == 2  # initial + 1 retry


@respx.mock
def test_llm_does_not_retry_on_4xx() -> None:
    route = respx.post(_URL).mock(return_value=Response(401, text="bad key"))
    provider = OpenAICompatibleLLMProvider(
        api_key="k", model="m", base_url="https://api.example.com/v1", max_retries=2
    )

    with pytest.raises(RuntimeError):
        provider.generate("sys", "prompt")
    assert route.call_count == 1  # 4xx is not retried
