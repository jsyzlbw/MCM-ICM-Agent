from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mcm_agent.core.gate_decision import GateDecision
from mcm_agent.utils.json_io import append_jsonl, read_json


StageHandler = Callable[[Path], list[str] | None]


class StageRunRecord(BaseModel):
    stage_id: str
    status: Literal["passed", "failed"]
    started_at: datetime
    finished_at: datetime
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    next_stage: str | None = None
    error: str | None = None


class StageExecutor:
    def __init__(
        self,
        workspace_root: Path,
        *,
        handlers: dict[str, StageHandler] | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.handlers = handlers or {}
        self.stage_log_path = workspace_root / "stage_runs.jsonl"
        self.stage_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.stage_log_path.exists():
            self.stage_log_path.write_text("", encoding="utf-8")

    def run_stage(self, stage_id: str) -> StageRunRecord:
        started_at = datetime.now(UTC)
        try:
            outputs = self._handler_for(stage_id)(self.workspace_root) or []
        except Exception as exc:
            record = StageRunRecord(
                stage_id=stage_id,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=str(exc),
            )
            append_jsonl(self.stage_log_path, record.model_dump(mode="json"))
            raise

        record = StageRunRecord(
            stage_id=stage_id,
            status="passed",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            outputs=outputs,
            next_stage=self.next_stage(stage_id),
        )
        append_jsonl(self.stage_log_path, record.model_dump(mode="json"))
        return record

    def next_stage(self, stage_id: str, *, condition: str = "pass") -> str | None:
        topology = read_json(self.workspace_root / "workflow_topology.json", {})
        for edge in topology.get("edges", []):
            if edge.get("from_node") == stage_id and edge.get("condition") == condition:
                return str(edge.get("to_node"))
        return None

    def route_failure(self, stage_id: str, failure_reason: str) -> str:
        topology = read_json(self.workspace_root / "workflow_topology.json", {})
        for route in topology.get("failure_routes", []):
            if (
                route.get("from_node") == stage_id
                and route.get("failure_reason") == failure_reason
            ):
                return str(route.get("to_node"))
        raise KeyError(f"missing failure route: {stage_id}/{failure_reason}")

    def next_stage_from_gate(self, decision: GateDecision) -> str | None:
        if decision.passed:
            return self.next_stage(decision.gate_id)
        if decision.repair_stage:
            return decision.repair_stage
        if decision.failure_reason:
            return self.route_failure(decision.gate_id, decision.failure_reason)
        return None

    def _handler_for(self, stage_id: str) -> StageHandler:
        try:
            return self.handlers[stage_id]
        except KeyError as exc:
            raise KeyError(f"missing stage handler: {stage_id}") from exc
