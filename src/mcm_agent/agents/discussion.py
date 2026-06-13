from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry


class UserDiscussionAgent:
    def confirm_direction(
        self,
        workspace_root: Path,
        mode: str,
        user_idea_summary: str,
        selected_route: str,
        paper_outline: str,
        decisions_to_preserve: list[str],
    ) -> None:
        discussion_dir = workspace_root / "discussion"
        discussion_dir.mkdir(parents=True, exist_ok=True)

        user_brief = "\n".join(
            [
                "# User Brief",
                "",
                f"Mode: {mode}",
                "",
                user_idea_summary,
                "",
            ]
        )
        (discussion_dir / "user_brief.md").write_text(user_brief, encoding="utf-8")

        decisions = "\n".join(f"- {decision}" for decision in decisions_to_preserve)
        confirmed = "\n".join(
            [
                "# Confirmed Direction",
                "",
                "## User Mode",
                mode,
                "",
                "## User Idea Summary",
                user_idea_summary,
                "",
                "## Selected Modeling Route",
                selected_route,
                "",
                "## Paper Outline",
                paper_outline,
                "",
                "## Decisions To Preserve",
                decisions or "- No explicit decisions yet.",
                "",
            ]
        )
        (discussion_dir / "confirmed_direction.md").write_text(confirmed, encoding="utf-8")

        registry = ArtifactRegistry(workspace_root / "artifact_registry.json")
        record = ArtifactRecord(
            artifact_id="confirmed_direction_v1",
            type="confirmed_direction",
            path="discussion/confirmed_direction.md",
            producer="UserDiscussionAgent",
            depends_on=["problem_understanding_v1"],
            status=ArtifactStatus.APPROVED,
            created_at=datetime.now(UTC),
        )
        try:
            registry.add(record)
        except ValueError:
            registry.update_status("confirmed_direction_v1", ArtifactStatus.APPROVED)

        Coordinator(workspace_root).emit(
            "user.direction.confirmed",
            payload={"artifact_ids": ["confirmed_direction_v1"]},
            source="UserDiscussionAgent",
        )
