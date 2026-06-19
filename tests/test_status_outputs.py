from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_status_shows_last_checkpoint(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")

    result = InteractiveSession(workspace.root).run_once("/status")

    assert "Workspace status" in result.message
    assert "Last checkpoint:" in result.message


def test_outputs_lists_generated_files(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    output = workspace.root / "output/draft/main.pdf"
    output.write_bytes(b"%PDF")

    result = InteractiveSession(workspace.root).run_once("/outputs")

    assert "output/draft/main.pdf" in result.message
