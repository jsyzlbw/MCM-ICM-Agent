from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_bang_runs_shell_and_echoes_output(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("!echo hi")

    assert "hi" in result.message
    assert "(exit 0)" in result.message


def test_bang_nonzero_exit_shown(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("!exit 2")

    assert "(exit 2)" in result.message


def test_bang_empty_shows_usage(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("!")

    assert "用法" in result.message
