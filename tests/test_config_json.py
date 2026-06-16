import json
from pathlib import Path

from mcm_agent.config import load_settings


def test_example_json_config_has_required_sections() -> None:
    config_path = Path("mcm_agent_config.example.json")

    payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert set(payload) == {
        "llm",
        "search",
        "official_data",
        "mineru",
        "humanizer",
        "rag",
        "embedding",
        "runtime",
    }
    assert payload["llm"]["provider"] == "openai_compatible"
    assert payload["rag"]["knowledge_base_dir"] == "knowledge_base"


def test_gitignore_keeps_local_config_and_user_knowledge_base_out_of_git() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "mcm_agent_config.local.json" in gitignore
    assert "knowledge_base/*" in gitignore
    assert "!knowledge_base/.gitkeep" in gitignore


def test_load_settings_uses_defaults_when_json_config_is_missing(tmp_path: Path) -> None:
    settings = load_settings(config_file=str(tmp_path / "missing.json"))

    assert settings.openai_model == "gpt-4.1"
    assert settings.rag_knowledge_base_dir == "knowledge_base"


def test_load_settings_overlays_json_values_over_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=env-openai",
                "OPENAI_MODEL=env-model",
                "TAVILY_API_KEY=env-tavily",
            ]
        ),
        encoding="utf-8",
    )
    config_file = tmp_path / "mcm_agent_config.local.json"
    config_file.write_text(
        json.dumps(
            {
                "llm": {
                    "api_key": "json-openai",
                    "base_url": "https://example.test/v1",
                    "model": "json-model",
                    "timeout_seconds": 12,
                },
                "search": {
                    "tavily_api_key": "json-tavily",
                    "firecrawl_api_key": "json-firecrawl",
                    "brave_search_api_key": "json-brave",
                    "exa_api_key": "json-exa",
                },
                "official_data": {
                    "fred_api_key": "json-fred",
                    "open_meteo_base_url": "https://weather.example/archive",
                    "oecd_base_url": "https://oecd.example",
                    "undata_base_url": "https://undata.example",
                    "us_census_api_key": "json-census",
                    "us_census_base_url": "https://census.example",
                    "noaa_api_key": "json-noaa",
                    "noaa_base_url": "https://noaa.example",
                    "nasa_power_base_url": "https://nasa.example",
                    "overpass_base_url": "https://overpass.example",
                },
                "mineru": {
                    "mode": "rest",
                    "cli": "mineru-json",
                    "api_base_url": "https://mineru.example",
                    "api_key": "json-mineru",
                },
                "humanizer": {
                    "api_key": "json-humanizer",
                    "api_base_url": "https://humanizer.example",
                },
                "rag": {
                    "knowledge_base_dir": "custom_knowledge",
                    "ingest_extensions": [".md", ".txt"],
                },
                "runtime": {
                    "default_language": "zh",
                    "max_retries": 5,
                    "http_timeout_seconds": 33,
                    "code_timeout_seconds": 44,
                },
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file=str(env_file), config_file=str(config_file))

    assert settings.openai_api_key == "json-openai"
    assert settings.openai_model == "json-model"
    assert settings.openai_base_url == "https://example.test/v1"
    assert settings.tavily_api_key == "json-tavily"
    assert settings.firecrawl_api_key == "json-firecrawl"
    assert settings.brave_search_api_key == "json-brave"
    assert settings.exa_api_key == "json-exa"
    assert settings.fred_api_key == "json-fred"
    assert settings.open_meteo_base_url == "https://weather.example/archive"
    assert settings.oecd_base_url == "https://oecd.example"
    assert settings.undata_base_url == "https://undata.example"
    assert settings.us_census_api_key == "json-census"
    assert settings.us_census_base_url == "https://census.example"
    assert settings.noaa_api_key == "json-noaa"
    assert settings.noaa_base_url == "https://noaa.example"
    assert settings.nasa_power_base_url == "https://nasa.example"
    assert settings.overpass_base_url == "https://overpass.example"
    assert settings.mineru_mode == "rest"
    assert settings.mineru_cli == "mineru-json"
    assert settings.mineru_api_base_url == "https://mineru.example"
    assert settings.mineru_api_key == "json-mineru"
    assert settings.humanizer_api_key == "json-humanizer"
    assert settings.humanizer_api_base_url == "https://humanizer.example"
    assert settings.rag_knowledge_base_dir == "custom_knowledge"
    assert settings.rag_ingest_extensions == [".md", ".txt"]
    assert settings.mcm_agent_default_language == "zh"
    assert settings.mcm_agent_max_retries == 5
    assert settings.mcm_agent_http_timeout_seconds == 33
    assert settings.mcm_agent_code_timeout_seconds == 44
