from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import write_json


class DataNeed(BaseModel):
    need_id: str
    description: str
    status: Literal["available", "needs_api", "manual_upload", "replace_plan"]
    recommendation: str


class DataAvailabilityMatrix(BaseModel):
    needs: list[DataNeed] = Field(default_factory=list)


class ResearchScript(BaseModel):
    title: str
    problem_path: str
    goals: list[str]
    data_availability: DataAvailabilityMatrix
    language: str = "en"
    locked: bool = False
    created_at: datetime


def build_initial_research_script(root: Path, language: str = "en") -> ResearchScript:
    problem_files = sorted((root / "input/problem").glob("*"))
    problem_path = str(problem_files[0].relative_to(root)) if problem_files else ""
    uploaded_data = sorted((root / "input/data").glob("*"))
    status = "available" if uploaded_data else "manual_upload"
    recommendation = (
        "Use uploaded contest data."
        if uploaded_data
        else "No contest data uploaded yet; continue with problem statement or run /data."
    )
    return ResearchScript(
        title="Mag modeling research script",
        problem_path=problem_path,
        goals=[
            "Understand the problem statement.",
            "Discuss candidate modeling directions with the user.",
            "Check critical data availability before locking the final script.",
        ],
        data_availability=DataAvailabilityMatrix(
            needs=[
                DataNeed(
                    need_id="contest_data",
                    description="Problem-provided data files, if any.",
                    status=status,  # type: ignore[arg-type]
                    recommendation=recommendation,
                )
            ]
        ),
        language=language,
        created_at=datetime.now(UTC),
    )


def write_research_script(root: Path, script: ResearchScript, locked: bool = False) -> None:
    target_dir = root / "work" / "discussion"
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = "locked_research_script" if locked else "research_script_draft"
    script.locked = locked
    write_json(target_dir / f"{stem}.json", script.model_dump(mode="json"))
    lines = [
        f"# {script.title}",
        "",
        f"Problem: `{script.problem_path}`",
        f"Paper language: `{script.language}`",
        "",
        "## Goals",
        *[f"- {goal}" for goal in script.goals],
        "",
        "## Data Availability",
        *[
            f"- `{need.need_id}`: {need.status}. {need.recommendation}"
            for need in script.data_availability.needs
        ],
    ]
    (target_dir / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
