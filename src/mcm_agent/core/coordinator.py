from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mcm_agent.core.events import EventLog
from mcm_agent.core.models import CheckpointDecision, EventRecord, TaskState
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.models import ArtifactStatus
from mcm_agent.utils.json_io import read_json, write_json


EVENT_PHASES = {
    "input.received": "input_received",
    "document.parsed": "document_parsed",
    "problem.understanding.ready": "awaiting_problem_understanding_approval",
    "data.feasibility.ready": "data_feasibility_ready",
    "data.feasibility.reframe_required": "research_reframing_required",
    "user.direction.confirmed": "direction_confirmed",
    "model.candidates.ready": "model_candidates_ready",
    "model.decision.ready": "awaiting_model_decision_approval",
    "model.decision.approved": "model_decision_approved",
    "data.ready": "data_ready",
    "code.completed": "code_completed",
    "validation.failed": "validation_failed",
    "validation.passed": "validation_passed",
    "figures.ready": "figures_ready",
    "paper.draft.ready": "awaiting_draft_review",
    "paper.review.failed": "paper_review_failed",
    "paper.review.passed": "paper_review_passed",
    "user.revision.requested": "revision_requested",
    "submission.ready": "submission_ready",
}

CHECKPOINT_EVENTS = {
    "problem.understanding.ready",
    "model.decision.ready",
    "paper.draft.ready",
    "submission.ready",
}


@dataclass(frozen=True)
class StatusSummary:
    current_phase: str
    unresolved_issue_count: int
    pending_checkpoints: int


class Coordinator:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.state_path = workspace_root / "task_state.json"
        self.event_log = EventLog(workspace_root / "event_log.jsonl")
        self.artifacts = ArtifactRegistry(workspace_root / "artifact_registry.json")

    def emit(
        self,
        event_type: str,
        *,
        payload: dict[str, object] | None = None,
        source: str = "Coordinator",
    ) -> str | None:
        payload = payload or {}
        now = datetime.now(UTC)
        event = EventRecord(
            event_id=f"event_{uuid4().hex[:12]}",
            event_type=event_type,
            payload=payload,
            created_at=now,
            source=source,
        )
        self.event_log.append(event)

        state = self._load_state()
        phase = EVENT_PHASES.get(event_type)
        if phase is not None:
            state = state.model_copy(update={"current_phase": phase, "updated_at": now})

        checkpoint_id: str | None = None
        if event_type in CHECKPOINT_EVENTS:
            artifact_ids = [str(item) for item in payload.get("artifact_ids", [])]
            checkpoint_id = f"checkpoint_{uuid4().hex[:12]}"
            checkpoint = CheckpointDecision(
                checkpoint_id=checkpoint_id,
                status="pending",
                approved_artifacts=artifact_ids,
                created_at=now,
            )
            state.checkpoints.append(checkpoint)

        self._write_state(state)
        return checkpoint_id

    def approve_checkpoint(self, checkpoint_id: str, user_message: str = "") -> None:
        state = self._load_state()
        checkpoints: list[CheckpointDecision] = []
        found = False
        now = datetime.now(UTC)
        for checkpoint in state.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                checkpoint = checkpoint.model_copy(
                    update={"status": "approved", "user_message": user_message}
                )
                found = True
                for artifact_id in checkpoint.approved_artifacts:
                    try:
                        self.artifacts.update_status(artifact_id, ArtifactStatus.APPROVED)
                    except KeyError:
                        continue
            checkpoints.append(checkpoint)

        if not found:
            raise KeyError(f"checkpoint not found: {checkpoint_id}")

        state = state.model_copy(update={"checkpoints": checkpoints, "updated_at": now})
        self._write_state(state)

    def status_summary(self) -> StatusSummary:
        state = self._load_state()
        pending = sum(1 for checkpoint in state.checkpoints if checkpoint.status == "pending")
        return StatusSummary(
            current_phase=state.current_phase,
            unresolved_issue_count=state.unresolved_issue_count,
            pending_checkpoints=pending,
        )

    def _load_state(self) -> TaskState:
        return TaskState.model_validate(read_json(self.state_path, {}))

    def _write_state(self, state: TaskState) -> None:
        write_json(self.state_path, state.model_dump(mode="json"))
