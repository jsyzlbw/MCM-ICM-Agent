from __future__ import annotations

import shutil
from pathlib import Path

from mcm_agent.agents.discussion import confirmed_language
from mcm_agent.agents.mock_judge import MockJudge, read_paper
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.core.problem_type import resolve_problem_type
from mcm_agent.utils.json_io import read_json, write_json

# Artifact dirs that constitute the shipped paper; snapshotted so the loop can
# restore the BEST-scoring iteration rather than shipping whatever the last
# (possibly regressed) repair produced. LLM repairs are noisy and non-monotonic.
_SNAPSHOT_DIRS = ("paper", "figures")
_BEST_SNAPSHOT = Path("review") / "mock_judge_best"

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

    def __init__(
        self,
        llm_provider: object | None = None,
        *,
        kb_dir: object | None = None,
        embedding: object | None = None,
        reranker: object | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.kb_dir = kb_dir
        self.embedding = embedding
        self.reranker = reranker

    def run(self, workspace_root: Path) -> list[str]:
        # 1. Read the paper and detect its language.
        text, figure_count = read_paper(workspace_root)
        language = confirmed_language(workspace_root)

        # 2. Resolve the problem type for anchored scoring (never raises).
        ptype = resolve_problem_type(workspace_root, self.llm_provider)

        # 3. Score the paper using consensus (denoised average of N samples).
        score = MockJudge(
            self.llm_provider,
            kb_dir=self.kb_dir,
            embedding=self.embedding,
            reranker=self.reranker,
        ).score_consensus(
            text, figure_count=figure_count, language=language, problem_type=ptype
        )

        # 4. Maintain a running history in review/mock_judge_scores.json.
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

        # 4b. Keep-best: snapshot this iteration's paper if it is the best scored so
        # far, so a later regressing repair cannot make us ship a worse paper.
        prior_totals = [entry["total"] for entry in history[:-1]]
        best_prior_total = max(prior_totals) if prior_totals else None
        if best_prior_total is None or score.total >= best_prior_total:
            self._snapshot_best(workspace_root)

        # 5. Decide PASS vs REPAIR.
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

        directive_path = workspace_root / "review" / "repair_directive.json"

        if should_pass:
            decision = GateDecision(
                gate_id="mock_judge_gate",
                status="pass",
                failure_reason=None,
                repair_stage=None,
                blocking_findings=[],
            )
            # Remove any stale repair directive so downstream stages are not misled.
            directive_path.unlink(missing_ok=True)
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

            # Write a targeted repair directive so the repair stage knows exactly
            # which dimension to address and what the judge said about it.
            write_json(
                directive_path,
                {
                    "target_stage": DIM_TO_STAGE[dim_label],
                    "weak_dimension": dim_label,
                    "score": dim_val,
                    "critique": score.comments.get(dim_label, ""),
                    "suggestions": score.revision_suggestions[:3],
                    "iteration": iteration,
                },
            )

        record_gate_decision(workspace_root, "mock_judge_gate.json", decision)

        # On a final pass, restore the best-scoring snapshot so the workflow packages
        # the best iteration's paper, not the last (which may have regressed).
        if should_pass:
            self._restore_best(workspace_root)

        return [
            "review/mock_judge_gate.json",
            "review/mock_judge_scores.json",
            "review/repair_directive.json",
        ]

    def _snapshot_best(self, workspace_root: Path) -> None:
        """Copy the current paper artifacts into the best-snapshot dir (best-effort)."""
        best_root = workspace_root / _BEST_SNAPSHOT
        for name in _SNAPSHOT_DIRS:
            src = workspace_root / name
            if not src.is_dir():
                continue
            dst = best_root / name
            try:
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            except Exception:
                pass  # snapshotting must never crash the gate

    def _restore_best(self, workspace_root: Path) -> None:
        """Restore the best-snapshot paper artifacts over the working ones (best-effort)."""
        best_root = workspace_root / _BEST_SNAPSHOT
        if not best_root.is_dir():
            return  # nothing snapshotted (e.g. single immediate pass) — keep current
        for name in _SNAPSHOT_DIRS:
            snap = best_root / name
            if not snap.is_dir():
                continue
            dst = workspace_root / name
            try:
                shutil.copytree(snap, dst, dirs_exist_ok=True)
            except Exception:
                pass  # restore must never crash the gate
