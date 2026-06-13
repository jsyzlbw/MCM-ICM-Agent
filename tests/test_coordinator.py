from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)


def _add_artifact(workspace: Path, artifact_id: str) -> None:
    ArtifactRegistry(workspace / "artifact_registry.json").add(
        ArtifactRecord(
            artifact_id=artifact_id,
            type="report",
            path=f"reports/{artifact_id}.md",
            producer="TestAgent",
            status=ArtifactStatus.REVIEW_REQUIRED,
            created_at=NOW,
        )
    )


def test_emit_event_updates_phase(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    coordinator = Coordinator(workspace.root)

    coordinator.emit("input.received", source="test")
    coordinator.emit("document.parsed", source="test")

    state = read_json(workspace.root / "task_state.json", {})
    assert state["current_phase"] == "document_parsed"


def test_data_feasibility_events_update_phase(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    coordinator = Coordinator(workspace.root)

    coordinator.emit("data.feasibility.ready", source="test")
    state = read_json(workspace.root / "task_state.json", {})
    assert state["current_phase"] == "data_feasibility_ready"

    coordinator.emit("data.feasibility.reframe_required", source="test")
    state = read_json(workspace.root / "task_state.json", {})
    assert state["current_phase"] == "research_reframing_required"


def test_problem_understanding_event_creates_pending_checkpoint(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _add_artifact(workspace.root, "problem_understanding_v1")

    coordinator = Coordinator(workspace.root)
    checkpoint_id = coordinator.emit(
        "problem.understanding.ready",
        payload={"artifact_ids": ["problem_understanding_v1"]},
        source="ProblemUnderstandingAgent",
    )

    state = read_json(workspace.root / "task_state.json", {})
    assert state["current_phase"] == "awaiting_problem_understanding_approval"
    assert state["checkpoints"][0]["checkpoint_id"] == checkpoint_id
    assert state["checkpoints"][0]["status"] == "pending"


def test_approve_checkpoint_marks_artifacts_approved(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _add_artifact(workspace.root, "problem_understanding_v1")
    coordinator = Coordinator(workspace.root)
    checkpoint_id = coordinator.emit(
        "problem.understanding.ready",
        payload={"artifact_ids": ["problem_understanding_v1"]},
        source="ProblemUnderstandingAgent",
    )

    coordinator.approve_checkpoint(checkpoint_id, user_message="Looks good.")

    state = read_json(workspace.root / "task_state.json", {})
    record = ArtifactRegistry(workspace.root / "artifact_registry.json").get(
        "problem_understanding_v1"
    )
    assert state["checkpoints"][0]["status"] == "approved"
    assert record.status == ArtifactStatus.APPROVED


def test_status_summary_counts_pending_checkpoints(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    coordinator = Coordinator(workspace.root)
    coordinator.emit(
        "paper.draft.ready",
        payload={"artifact_ids": ["paper_draft_v1"]},
        source="PaperWriterAgent",
    )

    summary = coordinator.status_summary()

    assert summary.current_phase == "awaiting_draft_review"
    assert summary.pending_checkpoints == 1
