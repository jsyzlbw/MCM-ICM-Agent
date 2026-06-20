import tomllib
from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.core.config_writer import set_env_var, set_toml_value
from mcm_agent.core.workspace import create_workspace


def test_set_env_var_upserts(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    set_env_var(root, "MAG_LLM_API_KEY", "k1")
    set_env_var(root, "MAG_LLM_API_KEY", "k2")
    set_env_var(root, "MAG_BRAVE_API_KEY", "b1")

    env = (root / ".env").read_text(encoding="utf-8")
    assert "MAG_LLM_API_KEY=k2" in env
    assert env.count("MAG_LLM_API_KEY=") == 1
    assert "MAG_BRAVE_API_KEY=b1" in env


def test_set_toml_value_roundtrip(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    set_toml_value(root, "llm", "model", "deepseek-v4-flash")
    set_toml_value(root, "llm", "base_url", "https://api.deepseek.com/v1")

    data = tomllib.loads((root / ".mag" / "config.toml").read_text(encoding="utf-8"))
    assert data["llm"]["model"] == "deepseek-v4-flash"
    assert data["llm"]["base_url"] == "https://api.deepseek.com/v1"


def test_config_writer_feeds_load_settings(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "w").root
    set_env_var(root, "MAG_BRAVE_API_KEY", "brave-key")
    set_toml_value(root, "llm", "model", "m1")

    settings = load_settings(workspace_root=root)
    assert settings.brave_search_api_key == "brave-key"
    assert settings.openai_model == "m1"
