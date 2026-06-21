from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mcm_agent.core.gate_decision import GateDecision
from mcm_agent.utils.json_io import append_jsonl, read_json, write_json


class StageResult(BaseModel):
    outputs: list[str] = Field(default_factory=list)
    condition: str = "pass"


class RepeatedGateFailureError(RuntimeError):
    def __init__(self, gate_id: str, failure_reason: str, repair_stage: str | None) -> None:
        self.gate_id = gate_id
        self.failure_reason = failure_reason
        self.repair_stage = repair_stage
        super().__init__(f"repeated gate failure: {gate_id}/{failure_reason}")


StageHandler = Callable[[Path], StageResult | list[str] | None]


GATE_DECISION_FILES = {
    "extraction_quality_gate": "review/extraction_gate.json",
    "source_verifier": "review/source_gate.json",
    "modeling_quality_gate": "review/modeling_gate.json",
    "validation_gate": "review/validation_gate.json",
    "figure_quality_gate": "review/figure_gate.json",
    "mock_judge_gate": "review/mock_judge_gate.json",
    "final_gatekeeper": "review/final_gate.json",
}


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
            result = self._coerce_result(self._handler_for(stage_id)(self.workspace_root))
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

        next_stage = self.next_stage(stage_id, condition=result.condition)
        gate_decision = self._gate_decision_for_stage(stage_id)
        if gate_decision is not None:
            next_stage = self.next_stage_from_gate(gate_decision)

        record = StageRunRecord(
            stage_id=stage_id,
            status="passed",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            outputs=result.outputs,
            next_stage=next_stage,
        )
        append_jsonl(self.stage_log_path, record.model_dump(mode="json"))
        self._update_task_state(stage_id)
        return record

    def run_until_complete(
        self,
        start_stage: str,
        *,
        terminal_stage: str | None = None,
        max_steps: int = 100,
        repeated_gate_limit: int = 3,
        controller: Callable[[StageRunRecord], str] | None = None,
    ) -> list[StageRunRecord]:
        records: list[StageRunRecord] = []
        gate_failures: dict[tuple[str, str], int] = {}
        current_stage: str | None = start_stage
        for _ in range(max_steps):
            if current_stage is None:
                break
            record = self.run_stage(current_stage)
            records.append(record)
            gate_decision = self._gate_decision_for_stage(record.stage_id)
            if gate_decision is not None and not gate_decision.passed:
                failure_reason = gate_decision.failure_reason or "unknown"
                key = (gate_decision.gate_id, failure_reason)
                gate_failures[key] = gate_failures.get(key, 0) + 1
                if gate_failures[key] >= repeated_gate_limit:
                    self._mark_blocked(gate_decision)
                    raise RepeatedGateFailureError(
                        gate_decision.gate_id,
                        failure_reason,
                        gate_decision.repair_stage,
                    )
            if terminal_stage is not None and current_stage == terminal_stage:
                break
            if controller is not None and controller(record) != "continue":
                break
            current_stage = record.next_stage
        else:
            raise RuntimeError(f"stage execution exceeded max_steps={max_steps}")
        return records

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

    def _coerce_result(self, value: StageResult | list[str] | None) -> StageResult:
        if value is None:
            return StageResult()
        if isinstance(value, StageResult):
            return value
        return StageResult(outputs=value)

    def _gate_decision_for_stage(self, stage_id: str) -> GateDecision | None:
        relative_path = GATE_DECISION_FILES.get(stage_id)
        if relative_path is None:
            return None
        payload = read_json(self.workspace_root / relative_path, None)
        if not payload:
            return None
        return GateDecision.model_validate(payload)

    def _update_task_state(self, stage_id: str) -> None:
        path = self.workspace_root / "task_state.json"
        state = read_json(path, {})
        if not isinstance(state, dict):
            return
        state["current_phase"] = stage_id
        state["updated_at"] = datetime.now(UTC).isoformat()
        write_json(path, state)

    def _mark_blocked(self, decision: GateDecision) -> None:
        path = self.workspace_root / "task_state.json"
        state = read_json(path, {})
        if not isinstance(state, dict):
            return
        failure_reason = decision.failure_reason or "unknown"
        state["current_phase"] = decision.gate_id
        state["blocked_reason"] = f"{decision.gate_id}/{failure_reason}"
        state["blocked_repair_stage"] = decision.repair_stage
        state["updated_at"] = datetime.now(UTC).isoformat()
        write_json(path, state)
