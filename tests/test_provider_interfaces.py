from pathlib import Path

import respx
from httpx import Response

from mcm_agent.config import load_settings
from mcm_agent.providers.base import ProviderBundle, ProviderResult
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.providers.llm import FakeLLMProvider, OpenAICompatibleLLMProvider
from mcm_agent.providers.search import TavilyProvider


def test_fake_llm_provider_returns_response_by_prompt_first_line() -> None:
    provider = FakeLLMProvider(
        {
            "problem_understanding": "structured report",
            "default": "fallback response",
        }
    )

    result = provider.generate("system", "problem_understanding\nRest of prompt")

    assert result == ProviderResult(content="structured report", metadata={"fake": True})


def test_fake_llm_provider_uses_default_response() -> None:
    provider = FakeLLMProvider({"default": "fallback response"})

    result = provider.generate("system", "unknown_prompt\nRest of prompt")

    assert result.content == "fallback response"


def test_settings_load_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_MODEL=test-model",
                "MINERU_MODE=fake",
                "HUMANIZER_API_BASE_URL=https://example.test",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(env_file))

    assert settings.openai_model == "test-model"
    assert settings.mineru_mode == "fake"
    assert settings.humanizer_api_base_url == "https://example.test"


def test_provider_bundle_accepts_fake_components() -> None:
    llm = FakeLLMProvider({"default": "ok"})
    bundle = ProviderBundle(
        llm=llm,
        mineru=object(),
        search=object(),
        extractor=object(),
        humanizer=object(),
        latex=object(),
    )

    assert bundle.llm.generate("", "").content == "ok"


@respx.mock
def test_openai_compatible_llm_provider_posts_chat_completion() -> None:
    respx.post("https://api.example.test/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "id": "chatcmpl_test",
                "choices": [{"message": {"content": "model response"}}],
                "usage": {"total_tokens": 12},
            },
        )
    )

    provider = OpenAICompatibleLLMProvider(
        api_key="key",
        model="test-model",
        base_url="https://api.example.test/v1",
    )
    result = provider.generate("system prompt", "user prompt", temperature=0.1)

    request = respx.calls.last.request
    assert request.headers["Authorization"] == "Bearer key"
    assert result.content == "model response"
    assert result.metadata["model"] == "test-model"
    assert result.metadata["total_tokens"] == 12


def test_provider_factory_uses_fake_providers_without_api_keys(tmp_path: Path) -> None:
    settings = load_settings()

    bundle = build_provider_bundle(settings, workspace_root=tmp_path)

    assert isinstance(bundle.llm, FakeLLMProvider)


def test_provider_factory_uses_real_search_when_key_is_present(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TAVILY_API_KEY=test-tavily",
                "FIRECRAWL_API_KEY=test-firecrawl",
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(str(env_file))

    bundle = build_provider_bundle(settings, workspace_root=tmp_path)

    assert isinstance(bundle.search, TavilyProvider)
