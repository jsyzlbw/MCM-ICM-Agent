from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4.1"

    tavily_api_key: str = ""
    firecrawl_api_key: str = ""
    brave_search_api_key: str = ""
    exa_api_key: str = ""

    fred_api_key: str = ""
    open_meteo_base_url: str = "https://archive-api.open-meteo.com/v1/archive"
    oecd_base_url: str = "https://sdmx.oecd.org/public/rest/v1/data"
    undata_base_url: str = "https://data.un.org/Handlers/DownloadHandler.ashx"
    us_census_api_key: str = ""
    us_census_base_url: str = "https://api.census.gov/data"
    noaa_api_key: str = ""
    noaa_base_url: str = "https://www.ncei.noaa.gov/cdo-web/api/v2"
    nasa_power_base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    overpass_base_url: str = "https://overpass-api.de/api/interpreter"

    humanizer_api_key: str = ""
    humanizer_api_base_url: str = "https://leahloveswriting.xyz"

    mineru_mode: str = "fake"
    mineru_cli: str = "mineru"
    mineru_api_base_url: str = "https://mineru.net"
    mineru_api_key: str = ""

    mcm_agent_default_language: str = "en"
    mcm_agent_max_retries: int = 2
    mcm_agent_http_timeout_seconds: int = 60
    mcm_agent_code_timeout_seconds: int = 120

    rag_knowledge_base_dir: str = "knowledge_base"
    rag_ingest_extensions: list[str] = [".md", ".txt", ".pdf"]

    embedding_provider: str = "fake"
    voyage_api_key: str = ""
    embedding_base_url: str = "https://api.voyageai.com/v1"
    embedding_model: str = "voyage-3-large"
    rerank_model: str = "rerank-2"

    model_config = SettingsConfigDict(extra="ignore")


def load_settings(env_file: str | None = None, config_file: str | None = None) -> Settings:
    settings = Settings(_env_file=env_file)
    if config_file is None:
        return settings

    path = Path(config_file)
    if not path.exists():
        return settings

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON config must be an object: {path}")
    overrides = _settings_overrides_from_json(payload)
    if not overrides:
        return settings
    return settings.model_copy(update=overrides)


def _settings_overrides_from_json(payload: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        ("llm", "api_key"): "openai_api_key",
        ("llm", "base_url"): "openai_base_url",
        ("llm", "model"): "openai_model",
        ("llm", "timeout_seconds"): "mcm_agent_http_timeout_seconds",
        ("search", "tavily_api_key"): "tavily_api_key",
        ("search", "firecrawl_api_key"): "firecrawl_api_key",
        ("search", "brave_search_api_key"): "brave_search_api_key",
        ("search", "exa_api_key"): "exa_api_key",
        ("official_data", "fred_api_key"): "fred_api_key",
        ("official_data", "open_meteo_base_url"): "open_meteo_base_url",
        ("official_data", "oecd_base_url"): "oecd_base_url",
        ("official_data", "undata_base_url"): "undata_base_url",
        ("official_data", "us_census_api_key"): "us_census_api_key",
        ("official_data", "us_census_base_url"): "us_census_base_url",
        ("official_data", "noaa_api_key"): "noaa_api_key",
        ("official_data", "noaa_base_url"): "noaa_base_url",
        ("official_data", "nasa_power_base_url"): "nasa_power_base_url",
        ("official_data", "overpass_base_url"): "overpass_base_url",
        ("mineru", "mode"): "mineru_mode",
        ("mineru", "cli"): "mineru_cli",
        ("mineru", "api_base_url"): "mineru_api_base_url",
        ("mineru", "api_key"): "mineru_api_key",
        ("humanizer", "api_key"): "humanizer_api_key",
        ("humanizer", "api_base_url"): "humanizer_api_base_url",
        ("rag", "knowledge_base_dir"): "rag_knowledge_base_dir",
        ("rag", "ingest_extensions"): "rag_ingest_extensions",
        ("embedding", "provider"): "embedding_provider",
        ("embedding", "api_key"): "voyage_api_key",
        ("embedding", "base_url"): "embedding_base_url",
        ("embedding", "embedding_model"): "embedding_model",
        ("embedding", "rerank_model"): "rerank_model",
        ("runtime", "default_language"): "mcm_agent_default_language",
        ("runtime", "max_retries"): "mcm_agent_max_retries",
        ("runtime", "http_timeout_seconds"): "mcm_agent_http_timeout_seconds",
        ("runtime", "code_timeout_seconds"): "mcm_agent_code_timeout_seconds",
    }
    overrides: dict[str, Any] = {}
    for (section_name, key), setting_name in mapping.items():
        section = payload.get(section_name, {})
        if isinstance(section, dict) and key in section:
            overrides[setting_name] = section[key]
    return overrides
