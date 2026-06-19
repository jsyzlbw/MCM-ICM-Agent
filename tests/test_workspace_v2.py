from pathlib import Path

from mcm_agent.core.workspace import (
    create_workspace,
    is_mag_workspace,
    load_workspace_state,
    save_workspace_state,
)
from mcm_agent.core.workspace_models import WorkspaceState
from mcm_agent.utils.json_io import read_json


def test_create_workspace_initializes_v2_layout(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")

    required_paths = [
        ".env",
        ".mag/workspace.json",
        ".mag/state.json",
        ".mag/config.toml",
        ".mag/chat/messages.jsonl",
        ".mag/events.jsonl",
        "input/problem",
        "input/data",
        "input/layout",
        "input/notes",
        "knowledge/papers",
        "knowledge/methods",
        "knowledge/rules",
        "knowledge/cases",
        "work/parsed",
        "work/reports",
        "work/discussion",
        "work/data",
        "work/results",
        "work/figures",
        "work/paper",
        "work/review",
        "output/draft",
        "output/final",
        "output/package",
    ]

    for relative_path in required_paths:
        assert (workspace.root / relative_path).exists(), relative_path


def test_workspace_metadata_and_state_are_machine_readable(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")

    metadata = read_json(workspace.root / ".mag/workspace.json", {})
    state = load_workspace_state(workspace.root)

    assert metadata["schema_version"] == 1
    assert metadata["workspace_id"] == "task"
    assert metadata["mag_version"] == "0.1.0"
    assert state.phase == "initialized"
    assert state.init.completed is False
    assert state.git.enabled is True


def test_is_mag_workspace_uses_v2_marker_files(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")

    assert is_mag_workspace(workspace.root)
    assert not is_mag_workspace(tmp_path / "not_workspace")


def test_workspace_state_round_trips(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "task")
    state = WorkspaceState(phase="init_complete", problem="input/problem/problem.pdf")

    save_workspace_state(workspace.root, state)

    loaded = load_workspace_state(workspace.root)
    assert loaded.phase == "init_complete"
    assert loaded.problem == "input/problem/problem.pdf"
