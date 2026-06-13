from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json, write_json


GateStatus = Literal["pass", "fail", "needs_user", "needs_repair"]


class GateDecision(BaseModel):
    gate_id: str
    status: GateStatus
    failure_reason: str | None = None
    repair_stage: str | None = None
    blocking_findings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def record_gate_decision(workspace_root: Path, filename: str, decision: GateDecision) -> None:
    decision_payload = decision.model_dump(mode="json")
    write_json(workspace_root / "review" / filename, decision_payload)

    log_path = workspace_root / "review" / "gate_decisions.json"
    existing = read_json(log_path, [])
    existing.append(decision_payload)
    write_json(log_path, existing)
