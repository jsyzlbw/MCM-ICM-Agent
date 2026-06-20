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
    analysis: str = ""
    language: str = "en"
    locked: bool = False
    created_at: datetime


_ANALYSIS_SYSTEM = (
    "You are Mag, an MCM/ICM math-modeling research assistant. Read the problem and "
    "produce a SHORT briefing the contestant can react to: (1) one paragraph on what the "
    "problem is really asking and its core difficulty; (2) 2-3 candidate modeling "
    "directions, each one line with a one-clause pro/con. Be concrete and specific to "
    "THIS problem. No preamble. Reply in {language}."
)

_LANG_NAMES = {"zh": "Chinese", "en": "English"}


def _analyze_problem(root: Path, llm: object, language: str) -> str:
    """One LLM call producing a discussable problem briefing. Returns '' on any
    failure so /start degrades to the static template instead of crashing."""
    problem_files = sorted((root / "input/problem").glob("*"))
    if not problem_files:
        return ""
    try:
        problem_text = problem_files[0].read_text(encoding="utf-8")[:6000]
    except (UnicodeDecodeError, OSError):
        return ""
    system = _ANALYSIS_SYSTEM.format(language=_LANG_NAMES.get(language, "English"))
    try:
        return llm.generate(system, f"PROBLEM:\n{problem_text}").content.strip()
    except Exception:  # noqa: BLE001 - analysis is best-effort; never block /start
        return ""


def build_initial_research_script(
    root: Path, language: str = "en", llm: object | None = None
) -> ResearchScript:
    problem_files = sorted((root / "input/problem").glob("*"))
    problem_path = str(problem_files[0].relative_to(root)) if problem_files else ""
    analysis = _analyze_problem(root, llm, language) if llm is not None else ""
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
        analysis=analysis,
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
    ]
    if script.analysis:
        lines += ["", "## 题目分析与候选方向", "", script.analysis]
    lines += [
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
