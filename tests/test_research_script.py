from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace, load_workspace_state


def _ready_workspace(tmp_path: Path) -> Path:
    workspace = create_workspace(tmp_path / "workspace")
    problem = tmp_path / "problem.md"
    problem.write_text("# Problem", encoding="utf-8")
    session = InteractiveSession(workspace.root)
    session.run_once(f"/question {problem}")
    session.run_once("/init --llm-key test-key")
    return workspace.root


def test_start_requires_llm(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)

    result = session.run_once("/start")

    assert "LLM API is required" in result.message


def test_start_requires_question_after_llm(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)
    session.run_once("/init --llm-key test-key")

    result = session.run_once("/start")

    assert "Run /question first" in result.message


def test_start_creates_research_script_draft(tmp_path: Path) -> None:
    root = _ready_workspace(tmp_path)
    session = InteractiveSession(root)

    result = session.run_once("/start")

    assert "Research script draft created" in result.message
    assert (root / "work/discussion/research_script_draft.md").exists()
    assert (root / "work/discussion/research_script_draft.json").exists()
    assert load_workspace_state(root).phase == "discussing"


def test_start_lock_creates_locked_research_script(tmp_path: Path) -> None:
    root = _ready_workspace(tmp_path)
    session = InteractiveSession(root)

    result = session.run_once("/start --lock")

    assert "Research script locked" in result.message
    assert (root / "work/discussion/locked_research_script.md").exists()
    assert (root / "work/discussion/locked_research_script.json").exists()
    assert load_workspace_state(root).phase == "script_locked"


def test_research_script_mentions_data_availability(tmp_path: Path) -> None:
    root = _ready_workspace(tmp_path)
    session = InteractiveSession(root)

    session.run_once("/start")

    text = (root / "work/discussion/research_script_draft.md").read_text(encoding="utf-8")
    assert "Data Availability" in text
    assert "contest_data" in text
