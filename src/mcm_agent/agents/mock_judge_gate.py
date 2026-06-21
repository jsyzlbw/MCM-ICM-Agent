from __future__ import annotations

from pathlib import Path

from mcm_agent.agents.discussion import confirmed_language
from mcm_agent.agents.mock_judge import MockJudge, read_paper
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.utils.json_io import read_json, write_json

# Minimum per-dimension score to avoid triggering a repair.
FLOOR = 4
# Minimum average total score to consider the paper good enough.
PASS_TOTAL = 6.0
# Maximum number of iterations before we force a pass regardless.
MAX_ITERS = 3

# Maps each rubric dimension to the stage that is responsible for fixing it.
DIM_TO_STAGE: dict[str, str] = {
    "figures": "figure_planning",
    "data_solution": "solver_coder",
    "validation": "solver_coder",
    "sensitivity": "solver_coder",
    "modeling": "paper_writer",
    "mathematics": "paper_writer",
    "writing": "paper_writer",
    "coherence": "paper_writer",
    "summary_sheet": "paper_writer",
    "problem_coverage": "paper_writer",
}


class MockJudgeGateAgent:
    """Score the assembled paper with MockJudge and route the weakest dimension
    back to the responsible repair stage unless the paper is good enough or we
    have exceeded the iteration cap."""

    def __init__(self, llm_provider: object | None = None) -> None:
        self.llm_provider = llm_provider

    def run(self, workspace_root: Path) -> list[str]:
        # 1. Read the paper and detect its language.
        text, figure_count = read_paper(workspace_root)
        language = confirmed_language(workspace_root)

        # 2. Score the paper.
        score = MockJudge(self.llm_provider).score(
            text, figure_count=figure_count, language=language
        )

        # 3. Maintain a running history in review/mock_judge_scores.json.
        scores_path = workspace_root / "review" / "mock_judge_scores.json"
        history: list[dict] = read_json(scores_path, [])
        history.append(
            {
                "iteration": len(history) + 1,
                "total": score.total,
                "dimensions": score.dimensions,
            }
        )
        write_json(scores_path, history)

        # 4. Decide PASS vs REPAIR.
        iteration = len(history)  # after append
        prev_total: float | None = history[-2]["total"] if len(history) >= 2 else None

        # Find the weakest scored dimension that has a repair stage mapping.
        weakest_dim: str | None = None
        weakest_score: int | None = None
        for dim in DIM_TO_STAGE:
            dim_score = score.dimensions.get(dim)
            if dim_score is None:
                continue
            if weakest_score is None or dim_score < weakest_score:
                weakest_dim = dim
                weakest_score = dim_score

        # Hard termination guards — always force a pass to prevent infinite loops.
        force_pass = (
            iteration >= MAX_ITERS
            or (prev_total is not None and score.total <= prev_total)
        )
        # Natural pass — quality meets the bar.
        natural_pass = (
            score.total >= PASS_TOTAL
            or weakest_score is None
            or weakest_score >= FLOOR
        )

        should_pass = force_pass or natural_pass

        if should_pass:
            decision = GateDecision(
                gate_id="mock_judge_gate",
                status="pass",
                failure_reason=None,
                repair_stage=None,
                blocking_findings=[],
            )
        else:
            # Build a short, informative finding line.
            dim_label = weakest_dim or "unknown"
            dim_val = weakest_score if weakest_score is not None else 0
            suggestions = score.revision_suggestions[:2]
            finding_parts = [f"Weak dimension '{dim_label}' scored {dim_val}/10."]
            finding_parts.extend(suggestions)
            blocking_findings = [" ".join(finding_parts)]

            decision = GateDecision(
                gate_id="mock_judge_gate",
                status="needs_repair",
                failure_reason=f"low_{dim_label}",
                repair_stage=DIM_TO_STAGE[dim_label],
                blocking_findings=blocking_findings,
            )

        record_gate_decision(workspace_root, "mock_judge_gate.json", decision)

        return ["review/mock_judge_gate.json", "review/mock_judge_scores.json"]
