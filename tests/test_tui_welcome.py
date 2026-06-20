from pathlib import Path

from rich.console import Console

from mcm_agent.config import load_settings
from mcm_agent.core.workspace import create_workspace, load_workspace_state
from mcm_agent.tui.theme import MAG_THEME
from mcm_agent.tui.welcome import render_welcome_panel


def _render(panel) -> str:
    console = Console(theme=MAG_THEME, width=80, file=None)
    with console.capture() as cap:
        console.print(panel)
    return cap.get()


def test_welcome_panel_shows_brand_and_next_step(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    out = _render(render_welcome_panel(state, settings, "0.1.0", root))

    assert "Mag" in out
    assert "∑" in out          # math brand glyph, not ✻
    assert "0.1.0" in out
    assert "Workspace" in out
    assert "/init" in out or "/api" in out  # next-step for a fresh workspace


def test_welcome_panel_shows_llm_when_configured(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    from mcm_agent.core.config_writer import set_env_var

    set_env_var(root, "MAG_LLM_API_KEY", "sk-x")
    set_env_var(root, "MAG_LLM_MODEL", "deepseek-v4-flash")
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    out = _render(render_welcome_panel(state, settings, "0.1.0", root))

    assert "deepseek-v4-flash" in out
