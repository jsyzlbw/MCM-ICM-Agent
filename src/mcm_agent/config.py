from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4.1"

    tavily_api_key: str = ""
    firecrawl_api_key: str = ""
    brave_search_api_key: str = ""
    exa_api_key: str = ""

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

    model_config = SettingsConfigDict(extra="ignore")


def load_settings(env_file: str | None = None) -> Settings:
    return Settings(_env_file=env_file)
