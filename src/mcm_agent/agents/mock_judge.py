from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

# The nine+ judging dimensions from the O-Prize rubric (see docs roadmap).
DIMENSIONS = [
    "summary_sheet",
    "problem_coverage",
    "modeling",
    "mathematics",
    "data_solution",
    "validation",
    "sensitivity",
    "figures",
    "writing",
    "coherence",
]


class RubricScore(BaseModel):
    dimensions: dict[str, int] = Field(default_factory=dict)
    comments: dict[str, str] = Field(default_factory=dict)
    revision_suggestions: list[str] = Field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(self.dimensions.values()) / max(len(self.dimensions), 1), 2)


def read_paper(root: Path) -> tuple[str, int]:
    """Return (concatenated section text, figure count) for a workspace."""
    section_dir = root / "paper" / "sections"
    text = ""
    if section_dir.exists():
        for tex in sorted(section_dir.glob("*.tex")):
            text += tex.read_text(encoding="utf-8") + "\n"
    figures = root / "figures"
    figure_count = 0
    if figures.exists():
        figure_count = sum(
            1 for f in figures.rglob("*") if f.suffix.lower() in {".pdf", ".png", ".svg", ".jpg"}
        )
    return text, figure_count


class MockJudge:
    """Scores a paper against the O-Prize rubric. Uses an LLM judge when available;
    otherwise a deterministic structural heuristic (so progress is measurable offline)."""

    def __init__(self, llm_provider: object | None = None) -> None:
        self.llm = llm_provider

    def score(self, paper_text: str, *, figure_count: int = 0, language: str = "en") -> RubricScore:
        if self.llm is None:
            return self._heuristic(paper_text, figure_count)
        try:
            raw = self.llm.generate(self._system(), self._prompt(paper_text, figure_count)).content
            data = self._parse(raw)
        except Exception:
            return self._heuristic(paper_text, figure_count)
        if not data:
            return self._heuristic(paper_text, figure_count)
        dims = {d: int(_clamp(data.get("dimensions", {}).get(d, 0))) for d in DIMENSIONS}
        return RubricScore(
            dimensions=dims,
            comments={str(k): str(v) for k, v in data.get("comments", {}).items()},
            revision_suggestions=[str(s) for s in data.get("revision_suggestions", []) if s],
        )

    def _system(self) -> str:
        return (
            "You are an MCM/ICM Outstanding-Winner judge. Score the paper on each rubric "
            "dimension from 0 (poor) to 10 (Outstanding). Respond ONLY with JSON: "
            '{"dimensions": {dim: int}, "comments": {dim: str}, "revision_suggestions": [str]}. '
            f"Dimensions: {', '.join(DIMENSIONS)}."
        )

    def _prompt(self, paper_text: str, figure_count: int) -> str:
        return "\n".join(
            [
                f"Figure count: {figure_count}",
                "Paper (LaTeX sections):",
                paper_text[:12000],
            ]
        )

    def _parse(self, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text.rstrip())
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _heuristic(self, paper_text: str, figure_count: int) -> RubricScore:
        lowered = paper_text.lower()
        length = len(paper_text)

        def has(*tokens: str) -> bool:
            return any(t in lowered for t in tokens)

        dims = {
            "summary_sheet": 6 if has("abstract", "摘要") and length > 400 else 3,
            "problem_coverage": min(10, 3 + paper_text.count("\\section")),
            "modeling": 6 if has("model", "模型") else 3,
            "mathematics": 7 if has("\\[", "equation", "\\frac", "$") else 3,
            "data_solution": 6 if has("data", "数据", "metric") else 3,
            "validation": 6 if has("validation", "验证", "cross-valid") else 2,
            "sensitivity": 7 if has("sensitivity", "敏感性", "robust") else 2,
            "figures": min(10, 2 + figure_count),
            "writing": 7 if length > 4000 else (5 if length > 1500 else 3),
            "coherence": 6 if "\\begin{tabular}" in paper_text or has("table") else 4,
        }
        dims = {k: int(_clamp(v)) for k, v in dims.items()}
        return RubricScore(
            dimensions=dims,
            comments={"_engine": "heuristic (no LLM judge configured)"},
            revision_suggestions=[
                s
                for s, ok in [
                    ("Add a real sensitivity analysis.", dims["sensitivity"] < 5),
                    ("Add validation against known/true values.", dims["validation"] < 5),
                    ("Add more informative figures.", figure_count < 4),
                ]
                if ok
            ],
        )


def _clamp(value: object) -> int:
    try:
        number = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, min(10, number))
