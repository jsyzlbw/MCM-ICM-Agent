from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace, load_workspace_state, save_workspace_state


def _ready_workspace_with_draft(tmp_path: Path) -> Path:
    workspace = create_workspace(tmp_path / "workspace")
    state = load_workspace_state(workspace.root)
    state.init.llm_configured = True
    state.init.problem_imported = True
    state.init.completed = True
    save_workspace_state(workspace.root, state)
    (workspace.root / "output/draft/main.tex").write_text("original draft", encoding="utf-8")
    return workspace.root


def test_feedback_after_draft_creates_revision_plan(tmp_path: Path) -> None:
    root = _ready_workspace_with_draft(tmp_path)
    session = InteractiveSession(root)

    result = session.run_once("第二问模型太简单，加入网络流模型")

    assert "Revision plan created" in result.message
    assert (root / "work/revisions/revision_001.md").exists()
    assert (root / "work/revisions/revision_001.json").exists()


def test_revision_plan_does_not_modify_existing_draft_before_confirmation(tmp_path: Path) -> None:
    root = _ready_workspace_with_draft(tmp_path)
    session = InteractiveSession(root)

    session.run_once("重写摘要")

    assert (root / "output/draft/main.tex").read_text(encoding="utf-8") == "original draft"


def test_revision_plan_contains_rerun_stages_and_expected_outputs(tmp_path: Path) -> None:
    root = _ready_workspace_with_draft(tmp_path)
    session = InteractiveSession(root)

    session.run_once("图 3 看不清，重画")

    text = (root / "work/revisions/revision_001.md").read_text(encoding="utf-8")
    assert "paper_writer" in text
    assert "typesetting" in text
    assert "output/draft/revision_001/main.pdf" in text
