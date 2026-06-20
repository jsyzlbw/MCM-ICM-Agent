from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.core.workspace import create_workspace, load_workspace_state
from mcm_agent.tui.statusbar import bottom_toolbar


def test_toolbar_shows_llm_and_phase(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    from mcm_agent.core.config_writer import set_env_var

    set_env_var(root, "MAG_LLM_API_KEY", "sk-x")
    set_env_var(root, "MAG_LLM_MODEL", "deepseek-v4-flash")
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    text = bottom_toolbar(state, settings)

    assert "deepseek-v4-flash" in text
    assert str(state.phase) in text


def test_toolbar_unconfigured_llm(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    assert "未配置" in bottom_toolbar(state, settings)
