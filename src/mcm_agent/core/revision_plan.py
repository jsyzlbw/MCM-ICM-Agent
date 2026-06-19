from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import write_json


class RevisionPlan(BaseModel):
    revision_id: str
    user_feedback: str
    affected_sections: list[str] = Field(default_factory=list)
    stages_to_rerun: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    confirmed: bool = False
    created_at: datetime


def next_revision_id(root: Path) -> str:
    revision_dir = root / "work" / "revisions"
    existing = sorted(revision_dir.glob("revision_*.json")) if revision_dir.exists() else []
    return f"revision_{len(existing) + 1:03d}"


def create_revision_plan(root: Path, feedback: str) -> RevisionPlan:
    revision_id = next_revision_id(root)
    plan = RevisionPlan(
        revision_id=revision_id,
        user_feedback=feedback,
        affected_sections=["paper", "figures", "review"],
        stages_to_rerun=["paper_writer", "typesetting", "pre_submission_review"],
        expected_outputs=[
            f"output/draft/{revision_id}/main.pdf",
            f"output/draft/{revision_id}/reviewer_report.md",
        ],
        created_at=datetime.now(UTC),
    )
    write_revision_plan(root, plan)
    return plan


def write_revision_plan(root: Path, plan: RevisionPlan) -> None:
    revision_dir = root / "work" / "revisions"
    revision_dir.mkdir(parents=True, exist_ok=True)
    write_json(revision_dir / f"{plan.revision_id}.json", plan.model_dump(mode="json"))
    md = [
        f"# {plan.revision_id}",
        "",
        "## User Feedback",
        "",
        plan.user_feedback,
        "",
        "## Stages To Re-run",
        *[f"- {stage}" for stage in plan.stages_to_rerun],
        "",
        "## Expected Outputs",
        *[f"- `{output}`" for output in plan.expected_outputs],
        "",
        "Proceed? [y/N]",
    ]
    (revision_dir / f"{plan.revision_id}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
