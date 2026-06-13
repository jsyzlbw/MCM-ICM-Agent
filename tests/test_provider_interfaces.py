from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.providers.base import ProviderBundle, ProviderResult
from mcm_agent.providers.llm import FakeLLMProvider


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
