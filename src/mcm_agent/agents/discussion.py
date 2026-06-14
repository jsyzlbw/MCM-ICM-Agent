from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.discussion_state import DiscussionDecision
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


class UserDiscussionAgent:
    def confirm_direction(
        self,
        workspace_root: Path,
        mode: str,
        user_idea_summary: str,
        selected_route: str,
        paper_outline: str,
        decisions_to_preserve: list[str],
        new_data_needs: list[str] | None = None,
    ) -> None:
        discussion_dir = workspace_root / "discussion"
        discussion_dir.mkdir(parents=True, exist_ok=True)
        new_data_needs = new_data_needs or []
        feasibility_snapshot = self._data_feasibility_snapshot(workspace_root)
        adopted_reframing = self._adopted_reframing_option(workspace_root)
        reframing_snapshot = self._reframing_snapshot(adopted_reframing)

        user_brief = "\n".join(
            [
                "# User Brief",
                "",
                f"Mode: {mode}",
                "",
                user_idea_summary,
                "",
                feasibility_snapshot,
                reframing_snapshot,
            ]
        )
        (discussion_dir / "user_brief.md").write_text(user_brief, encoding="utf-8")
        decision = DiscussionDecision(
            status="needs_data_scout" if new_data_needs else "locked",
            selected_route=selected_route,
            new_data_needs=new_data_needs,
            adopted_reframing_strategy=str(adopted_reframing.get("strategy", "")),
            adopted_reframing_option_id=self._reframing_option_id(adopted_reframing),
        )
        write_json(discussion_dir / "direction_lock.json", decision.model_dump(mode="json"))
        write_json(discussion_dir / "data_questions.json", new_data_needs)
        if decision.requires_data_scout:
            Coordinator(workspace_root).emit(
                "discussion.new_data_requested",
                payload={"new_data_needs": new_data_needs},
                source="UserDiscussionAgent",
            )
            return

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
                feasibility_snapshot,
                "",
                reframing_snapshot,
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

    def _data_feasibility_snapshot(self, workspace_root: Path) -> str:
        matrix = read_json(workspace_root / "data" / "data_feasibility_matrix.json", [])
        if not isinstance(matrix, list) or not matrix:
            return ""
        lines = ["## Data Feasibility Snapshot", ""]
        for row in matrix:
            if not isinstance(row, dict):
                continue
            target = row.get("target_dataset", "unknown data need")
            availability = row.get("availability", "unknown")
            confidence = row.get("confidence", "unknown")
            action = row.get("recommended_action", "Review before modeling.")
            lines.append(f"- {target}: {availability} (confidence: {confidence}). {action}")
            proxy_variables = row.get("proxy_variables", [])
            if isinstance(proxy_variables, list) and proxy_variables:
                lines.append("  Proxy variables: " + ", ".join(str(item) for item in proxy_variables))
        lines.append("")
        return "\n".join(lines)

    def _adopted_reframing_option(self, workspace_root: Path) -> dict[str, object]:
        options = read_json(workspace_root / "discussion" / "reframing_options.json", [])
        if not isinstance(options, list):
            return {}
        valid_options = [option for option in options if isinstance(option, dict)]
        for option in valid_options:
            if option.get("strategy") == "proxy_modeling":
                return option
        return valid_options[0] if valid_options else {}

    def _reframing_option_id(self, option: dict[str, object]) -> str:
        if not option:
            return ""
        return f"{option.get('data_need_id', 'unknown')}:{option.get('strategy', 'unknown')}"

    def _reframing_snapshot(self, option: dict[str, object]) -> str:
        if not option:
            return ""
        lines = [
            "## Adopted Reframing Option",
            "",
            f"- Option ID: `{self._reframing_option_id(option)}`",
            f"- Strategy: {option.get('strategy', '')}",
            f"- Target dataset: {option.get('target_dataset', '')}",
            f"- Recommended model change: {option.get('recommended_model_change', '')}",
            f"- Risk note: {option.get('risk_note', '')}",
        ]
        proxy_variables = option.get("proxy_variables", [])
        if isinstance(proxy_variables, list) and proxy_variables:
            lines.append("- Proxy variables: " + ", ".join(str(item) for item in proxy_variables))
        lines.append("")
        return "\n".join(lines)
