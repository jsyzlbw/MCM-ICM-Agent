from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_question_mark_shows_shortcuts(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("?")

    assert "快捷键" in result.message
    assert "Ctrl+C" in result.message
    assert "!" in result.message and "@" in result.message
