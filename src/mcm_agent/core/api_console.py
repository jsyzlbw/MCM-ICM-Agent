from __future__ import annotations

from pathlib import Path
from typing import Any

from mcm_agent.config import load_settings
from mcm_agent.core.config_writer import set_env_var

# Each provider: editable fields (name, .env var, is_secret), the smoke check id,
# and the Settings attribute used to report "configured".
PROVIDERS: list[dict[str, Any]] = [
    {
        "key": "llm",
        "label": "LLM",
        "required": True,
        "fields": [
            ("api_key", "MAG_LLM_API_KEY", True),
            ("base_url", "MAG_LLM_BASE_URL", False),
            ("model", "MAG_LLM_MODEL", False),
        ],
        "smoke": "llm",
        "setting": "openai_api_key",
        "detail_setting": "openai_model",
    },
    {"key": "tavily", "label": "Tavily Search", "fields": [("api_key", "MAG_TAVILY_API_KEY", True)],
     "smoke": "tavily", "setting": "tavily_api_key"},
    {"key": "brave", "label": "Brave Search", "fields": [("api_key", "MAG_BRAVE_API_KEY", True)],
     "smoke": "brave", "setting": "brave_search_api_key"},
    {"key": "exa", "label": "Exa Search", "fields": [("api_key", "MAG_EXA_API_KEY", True)],
     "smoke": "exa", "setting": "exa_api_key"},
    {"key": "firecrawl", "label": "Firecrawl", "fields": [("api_key", "MAG_FIRECRAWL_API_KEY", True)],
     "smoke": "firecrawl", "setting": "firecrawl_api_key"},
    {"key": "mineru", "label": "MinerU (PDF)", "fields": [("api_key", "MAG_MINERU_API_KEY", True)],
     "smoke": "mineru", "setting": "mineru_api_key"},
    {"key": "embedding", "label": "Embedding (Voyage)", "fields": [("api_key", "MAG_VOYAGE_API_KEY", True)],
     "smoke": "embedding", "setting": "voyage_api_key"},
    {"key": "humanizer", "label": "Humanizer", "fields": [("api_key", "MAG_HUMANIZER_API_KEY", True)],
     "smoke": "humanizer", "setting": "humanizer_api_key"},
]


def _provider(key: str) -> dict[str, Any]:
    for provider in PROVIDERS:
        if provider["key"] == key:
            return provider
    raise KeyError(f"unknown provider: {key}")


def provider_status(root: Path) -> list[dict[str, Any]]:
    settings = load_settings(workspace_root=root)
    rows = []
    for provider in PROVIDERS:
        configured = bool(getattr(settings, provider["setting"], ""))
        detail = ""
        if configured and provider.get("detail_setting"):
            detail = str(getattr(settings, provider["detail_setting"], ""))
        rows.append(
            {
                "key": provider["key"],
                "label": provider["label"],
                "required": provider.get("required", False),
                "configured": configured,
                "detail": detail,
            }
        )
    return rows


def provider_fields(key: str) -> list[tuple[str, str, bool]]:
    return list(_provider(key)["fields"])


def set_provider(root: Path, key: str, answers: dict[str, str]) -> None:
    """Persist a provider's configuration. All values go to the workspace .env."""
    for field_name, env_var, _is_secret in _provider(key)["fields"]:
        value = answers.get(field_name)
        if value:
            set_env_var(root, env_var, value)


def check_provider(root: Path, key: str, tester: object | None = None) -> dict[str, str]:
    """Run a real connectivity smoke for the provider; returns {status, detail}."""
    smoke_id = _provider(key)["smoke"]
    if tester is None:
        from mcm_agent.providers.smoke import ProviderSmokeTester

        tester = ProviderSmokeTester(load_settings(workspace_root=root), workspace_root=Path(root))
    result = tester.check(smoke_id)
    status = getattr(result, "status", "failed")
    return {"status": str(getattr(status, "value", status)), "detail": getattr(result, "detail", "")}
