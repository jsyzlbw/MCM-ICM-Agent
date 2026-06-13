from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from mcm_agent.core.models import HandoffPacket


def create_handoff_packet(
    *,
    from_agent: str,
    to_agent: str,
    task: str,
    input_artifacts: list[str],
    expected_outputs: list[str],
    acceptance_criteria: list[str],
    known_risks: list[str] | None = None,
) -> HandoffPacket:
    return HandoffPacket(
        handoff_id=f"handoff_{uuid4().hex[:12]}",
        from_agent=from_agent,
        to_agent=to_agent,
        task=task,
        input_artifacts=input_artifacts,
        expected_outputs=expected_outputs,
        acceptance_criteria=acceptance_criteria,
        known_risks=known_risks or [],
        created_at=datetime.now(UTC),
    )
