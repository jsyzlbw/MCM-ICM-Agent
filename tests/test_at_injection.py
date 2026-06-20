from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_collect_attachments_reads_existing_workspace_file(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "notes.txt").write_text("hello-content", encoding="utf-8")
    session = InteractiveSession(root)

    atts = session._collect_attachments("解释 @notes.txt 里的内容")

    assert atts == [("notes.txt", "hello-content")]


def test_collect_attachments_ignores_missing(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    assert session._collect_attachments("看 @nope.txt") == []
