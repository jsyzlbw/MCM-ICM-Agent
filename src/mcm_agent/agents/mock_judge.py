from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean

from pydantic import BaseModel, Field

from mcm_agent.corpus.reference import build_reference_block

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


# A full MCM/ICM paper's LaTeX sources run ~30–60k chars. The old 12k cap made the
# judge BLIND to the model/results/sensitivity sections + most figures once the writer
# produced substantive papers — under-scoring good work AND misrouting the O6 repair
# loop. deepseek-v4-pro and peers have ample context, so read the whole paper.
MAX_JUDGE_PAPER_CHARS = 60000


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
    otherwise a deterministic structural heuristic (so progress is measurable offline).

    Anchored mode (kb_dir + problem_type provided at score-time):
        Retrieves real Outstanding-paper reference material and scores the candidate
        RELATIVE to that bar (9-10 = matches O-level, 7-8 = strong, 5-6 = competent,
        <=4 = weak). Every dimension score must cite specific content from the candidate.

    Absolute mode (fallback when no KB or empty reference):
        Uses the original 0-10 absolute rubric. Labeled as 'absolute(uncalibrated)' in
        comments['_mode'] to make the uncalibrated nature explicit.
    """

    def __init__(
        self,
        llm_provider: object | None = None,
        *,
        kb_dir: Path | None = None,
        embedding: object | None = None,
        reranker: object | None = None,
    ) -> None:
        self.llm = llm_provider
        self.kb_dir = Path(kb_dir) if kb_dir is not None else None
        self.embedding = embedding
        self.reranker = reranker

    def score(
        self,
        paper_text: str,
        *,
        figure_count: int = 0,
        language: str = "en",
        problem_type: str | None = None,
        exclude_paper_id: str | None = None,
    ) -> RubricScore:
        if self.llm is None:
            return self._heuristic(paper_text, figure_count)

        # Try anchored mode if we have the required deps
        if self.kb_dir is not None and problem_type is not None:
            try:
                ref = build_reference_block(
                    self.kb_dir,
                    problem_type,
                    query=paper_text[:500],
                    embedding=self.embedding,
                    reranker=self.reranker,
                    exclude_paper_id=exclude_paper_id,
                )
            except Exception:
                ref = ""

            if ref:
                try:
                    raw = self.llm.generate(
                        self._anchored_system(),
                        self._anchored_prompt(paper_text, figure_count, ref),
                    ).content
                    data = self._parse(raw)
                except Exception:
                    return self._heuristic(paper_text, figure_count)

                if not data:
                    return self._heuristic(paper_text, figure_count)

                dims = {d: int(_clamp(data.get("dimensions", {}).get(d, 0))) for d in DIMENSIONS}
                comments = {str(k): str(v) for k, v in data.get("comments", {}).items()}
                comments["_mode"] = "anchored"
                return RubricScore(
                    dimensions=dims,
                    comments=comments,
                    revision_suggestions=[str(s) for s in data.get("revision_suggestions", []) if s],
                )

        # Absolute mode (no KB, no problem_type, or empty reference)
        try:
            raw = self.llm.generate(self._system(), self._prompt(paper_text, figure_count)).content
            data = self._parse(raw)
        except Exception:
            return self._heuristic(paper_text, figure_count)

        if not data:
            return self._heuristic(paper_text, figure_count)

        dims = {d: int(_clamp(data.get("dimensions", {}).get(d, 0))) for d in DIMENSIONS}
        comments = {str(k): str(v) for k, v in data.get("comments", {}).items()}
        comments["_mode"] = "absolute(uncalibrated)"
        return RubricScore(
            dimensions=dims,
            comments=comments,
            revision_suggestions=[str(s) for s in data.get("revision_suggestions", []) if s],
        )

    def score_consensus(
        self,
        paper_text: str,
        *,
        figure_count: int = 0,
        language: str = "en",
        samples: int = 3,
        problem_type: str | None = None,
        exclude_paper_id: str | None = None,
    ) -> RubricScore:
        """Return a denoised score by averaging N independent judge calls.

        When no LLM is configured the heuristic is already deterministic, so
        a single call is returned directly to avoid pointless duplication.
        ``samples`` < 1 is treated as 1.
        """
        if self.llm is None:
            return self.score(
                paper_text,
                figure_count=figure_count,
                language=language,
                problem_type=problem_type,
                exclude_paper_id=exclude_paper_id,
            )

        n = max(1, samples)
        sample_scores: list[RubricScore] = [
            self.score(
                paper_text,
                figure_count=figure_count,
                language=language,
                problem_type=problem_type,
                exclude_paper_id=exclude_paper_id,
            )
            for _ in range(n)
        ]

        # Average each dimension across all samples, round to int.
        dims: dict[str, int] = {
            d: round(mean(s.dimensions.get(d, 0) for s in sample_scores))
            for d in DIMENSIONS
        }

        # Pick the sample whose total is closest to the mean total for prose fields.
        mean_total = mean(s.total for s in sample_scores)
        representative = min(sample_scores, key=lambda s: abs(s.total - mean_total))

        return RubricScore(
            dimensions=dims,
            comments=representative.comments,
            revision_suggestions=representative.revision_suggestions,
        )

    def _system(self) -> str:
        completeness_gate = (
            "COMPLETENESS IS A HARD GATE. "
            "First identify how many distinct tasks/sub-questions the problem requires (T) "
            "and how many the paper SUBSTANTIVELY answers (A) — a task that is only mentioned "
            "or gestured at does NOT count as answered. "
            "Score problem_coverage proportionally to A/T: a paper that substantively answers "
            "only some of the required tasks MUST receive a low problem_coverage regardless of "
            "how well the answered tasks are done "
            "(e.g. answering 1 of 4 tasks => problem_coverage <= 3; 2 of 4 => <= 5). "
            "In revision_suggestions, explicitly name each required task the paper failed to answer."
        )
        return (
            "You are an MCM/ICM Outstanding-Winner judge. Score the paper on each rubric "
            "dimension from 0 (poor) to 10 (Outstanding). Respond ONLY with JSON: "
            '{"dimensions": {dim: int}, "comments": {dim: str}, "revision_suggestions": [str]}. '
            f"Dimensions: {', '.join(DIMENSIONS)}. "
            f"{completeness_gate}"
        )

    def _anchored_system(self) -> str:
        """System prompt for anchored relative-scoring mode.

        Scores the candidate RELATIVE to real Outstanding work provided as reference.
        Each dimension score must be grounded in specific evidence from the candidate.
        """
        completeness_gate = (
            "COMPLETENESS IS A HARD GATE. "
            "First identify how many distinct tasks/sub-questions the problem requires (T) "
            "and how many the paper SUBSTANTIVELY answers (A) — a task that is only mentioned "
            "or gestured at does NOT count as answered. "
            "Score problem_coverage proportionally to A/T: a paper that substantively answers "
            "only some of the required tasks MUST receive a low problem_coverage regardless of "
            "how well the answered tasks are done "
            "(e.g. answering 1 of 4 tasks => problem_coverage <= 3; 2 of 4 => <= 5). "
            "In revision_suggestions, explicitly name each required task the paper failed to answer."
        )
        dims_list = ", ".join(DIMENSIONS)
        return (
            "You are an MCM/ICM judge. "
            "You are given REFERENCE material from REAL Outstanding papers of this problem type. "
            "Score the CANDIDATE paper RELATIVE to that Outstanding bar on each of the 10 "
            f"dimensions (0-10): "
            "9-10 = matches or exceeds the reference's rigor and completeness; "
            "7-8 = clearly strong but below the reference; "
            "5-6 = competent; "
            "3-4 = weak; "
            "0-2 = absent/wrong. "
            "For EVERY dimension you MUST justify the score by citing SPECIFIC content from the "
            "candidate (an equation, a metric value, a table, a named method); "
            "a claim asserted without substantiating content in the candidate scores LOW — "
            "evidence is required, not just assertion. "
            "The `figures` dimension: judge ONLY from the candidate's own figure_count and "
            "figure-related content — do NOT compare figures to the reference "
            "(the reference text has no figures). "
            f"{completeness_gate} "
            "Output ONLY JSON "
            '{"dimensions": {dim: int}, "comments": {dim: str}, "revision_suggestions": [str]}. '
            f"Dimensions: {dims_list}."
        )

    def _prompt(self, paper_text: str, figure_count: int) -> str:
        return "\n".join(
            [
                f"Figure count: {figure_count}",
                "Paper (LaTeX sections):",
                paper_text[:MAX_JUDGE_PAPER_CHARS],
            ]
        )

    def _anchored_prompt(self, paper_text: str, figure_count: int, ref: str) -> str:
        """Prompt for anchored mode: reference block first, then candidate."""
        return "\n\n".join(
            [
                ref,
                f"Figure count: {figure_count}",
                "CANDIDATE paper (LaTeX sections):",
                paper_text[:MAX_JUDGE_PAPER_CHARS],
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
