"""Tests for MockJudgeGateAgent (O6: self-eval closed loop).

All tests are offline and deterministic — no real LLM or kernel is used.
We stub the LLM the same way test_mock_judge.py does (_JudgeLLM pattern).
"""
from __future__ import annotations

import json
from pathlib import Path


from mcm_agent.agents.mock_judge import DIMENSIONS
from mcm_agent.agents.mock_judge_gate import MAX_ITERS, MockJudgeGateAgent
from mcm_agent.core.stage_executor import GATE_DECISION_FILES
from mcm_agent.core.workflow_graph import build_default_workflow_graph
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult
from mcm_agent.utils.json_io import read_json, write_json


# ---------------------------------------------------------------------------
# Stub LLM helpers
# ---------------------------------------------------------------------------


class _StubbedLLM:
    """Fake LLM that returns a pre-canned RubricScore-shaped JSON payload."""

    def __init__(self, dimensions: dict[str, int], revision_suggestions: list[str] | None = None):
        self._dims = dimensions
        self._suggestions = revision_suggestions or []

    def generate(self, system: str, prompt: str, **kwargs: object) -> ProviderResult:
        payload = {
            "dimensions": self._dims,
            "comments": {d: "ok" for d in self._dims},
            "revision_suggestions": self._suggestions,
        }
        return ProviderResult(
            content="```json\n" + json.dumps(payload) + "\n```",
            metadata={},
        )


def _make_workspace(tmp_path: Path, *, with_paper: bool = True) -> Path:
    """Create a minimal workspace; optionally add a paper section so read_paper is non-trivial."""
    ws = create_workspace(tmp_path / "ws").root
    if with_paper:
        section_dir = ws / "paper" / "sections"
        section_dir.mkdir(parents=True, exist_ok=True)
        (section_dir / "intro.tex").write_text(
            r"\section{Introduction} This is a test paper with sensitivity analysis and validation.",
            encoding="utf-8",
        )
    return ws


def _all_floor_except(low_dim: str, low_score: int = 1) -> dict[str, int]:
    """Return a dimension dict where one dim is low and all others are exactly FLOOR.

    This keeps total < PASS_TOTAL so the FLOOR-based repair path is exercised.
    With 10 dims, all at FLOOR=4 except one at low_score:
      total = (4*9 + low_score) / 10 = (36 + low_score) / 10
    For low_score=1 → total=3.7 < PASS_TOTAL=6.0 → repair path active.
    """
    from mcm_agent.agents.mock_judge_gate import FLOOR

    return {d: (low_score if d == low_dim else FLOOR) for d in DIMENSIONS}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_low_figures_routes_to_figure_planning(tmp_path: Path) -> None:
    """figures dim is lowest and below FLOOR; total < PASS_TOTAL → needs_repair."""
    ws = _make_workspace(tmp_path)
    llm = _StubbedLLM(
        dimensions=_all_floor_except("figures", low_score=1),
        revision_suggestions=["Add more informative figures.", "Include flow charts."],
    )

    agent = MockJudgeGateAgent(llm)
    outputs = agent.run(ws)

    decision_raw = read_json(ws / "review" / "mock_judge_gate.json", {})
    assert decision_raw["status"] == "needs_repair"
    assert decision_raw["repair_stage"] == "figure_planning"
    assert decision_raw["failure_reason"] == "low_figures"

    scores = read_json(ws / "review" / "mock_judge_scores.json", [])
    assert len(scores) == 1

    assert "review/mock_judge_gate.json" in outputs
    assert "review/mock_judge_scores.json" in outputs


def test_low_validation_routes_to_solver_coder(tmp_path: Path) -> None:
    """validation dim is lowest and below FLOOR; total < PASS_TOTAL → needs_repair → solver_coder."""
    ws = _make_workspace(tmp_path)
    llm = _StubbedLLM(dimensions=_all_floor_except("validation", low_score=2))

    MockJudgeGateAgent(llm).run(ws)

    decision_raw = read_json(ws / "review" / "mock_judge_gate.json", {})
    assert decision_raw["status"] == "needs_repair"
    assert decision_raw["repair_stage"] == "solver_coder"
    assert decision_raw["failure_reason"] == "low_validation"


def test_high_scores_pass(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    # All dimensions at 8 → total = 8.0 ≥ PASS_TOTAL and nothing below FLOOR.
    llm = _StubbedLLM(dimensions={d: 8 for d in DIMENSIONS})

    MockJudgeGateAgent(llm).run(ws)

    decision_raw = read_json(ws / "review" / "mock_judge_gate.json", {})
    assert decision_raw["status"] == "pass"


def test_high_total_passes_even_with_a_weak_dim(tmp_path: Path) -> None:
    """Hard pass: total >= PASS_TOTAL overrides a weak single dimension.

    Nine dims at 8 and one dim (figures) at 1:
      total = (8*9 + 1) / 10 = 73/10 = 7.3 >= PASS_TOTAL=6.0 → status=="pass"
    despite figures being well below FLOOR=4.
    """
    ws = _make_workspace(tmp_path)
    dims = {d: 8 for d in DIMENSIONS}
    dims["figures"] = 1  # single weak dimension
    llm = _StubbedLLM(dimensions=dims)

    MockJudgeGateAgent(llm).run(ws)

    decision_raw = read_json(ws / "review" / "mock_judge_gate.json", {})
    assert decision_raw["status"] == "pass", (
        "total >= PASS_TOTAL must be a hard pass even when a dimension is below FLOOR."
    )


def test_passes_at_max_iters_even_if_low(tmp_path: Path) -> None:
    """TERMINATION GUARD: iteration >= MAX_ITERS must force a pass even when quality is low.

    Isolation invariant: the not-improving guard must NOT fire so that ONLY the
    MAX_ITERS guard can cause the pass.  We guarantee this by seeding strictly
    increasing prior totals and returning a new total higher than the last prior
    entry, so ``score.total > prev_total`` (not-improving guard is silent).

    The dimensions are all-below-FLOOR (score 2) with total 3.0 < PASS_TOTAL=6.0,
    so neither the natural-pass nor the not-improving guard would trigger a pass.
    Only ``iteration >= MAX_ITERS`` saves us.

    Removing the ``iteration >= MAX_ITERS`` clause from mock_judge_gate.py makes
    this test fail because none of the remaining guards produce "pass" for these scores.
    """
    ws = _make_workspace(tmp_path)

    # Pre-seed MAX_ITERS-1 entries with STRICTLY INCREASING totals (1.0, 2.0, …)
    # so the last entry has total = float(MAX_ITERS - 1).
    prior_history = [
        {
            "iteration": i + 1,
            "total": float(i + 1),
            "dimensions": {d: 2 for d in DIMENSIONS},
        }
        for i in range(MAX_ITERS - 1)
    ]
    write_json(ws / "review" / "mock_judge_scores.json", prior_history)

    # Judge returns total = 3.0 > last prior total (MAX_ITERS-1), so
    # not-improving guard does NOT fire.  Dims still below FLOOR → needs_repair
    # normally, but MAX_ITERS guard must force "pass".
    # With 10 dims all at score 3: total = 3.0.  PASS_TOTAL=6.0, FLOOR=4 → both
    # the total-based and floor-based natural passes are inactive.
    new_total = float(MAX_ITERS)  # strictly > last prior entry (MAX_ITERS - 1)
    assert new_total > float(MAX_ITERS - 1), "test setup: new total must exceed last prior"
    llm = _StubbedLLM(dimensions={d: 3 for d in DIMENSIONS})  # avg = 3.0

    MockJudgeGateAgent(llm).run(ws)

    decision_raw = read_json(ws / "review" / "mock_judge_gate.json", {})
    assert decision_raw["status"] == "pass", (
        "Gate must pass at MAX_ITERS to prevent infinite loops "
        "(only the iteration>=MAX_ITERS guard should have fired here)."
    )

    scores = read_json(ws / "review" / "mock_judge_scores.json", [])
    assert len(scores) == MAX_ITERS


def test_passes_when_not_improving(tmp_path: Path) -> None:
    """If the score is not improving (total <= prev_total), force a pass to avoid looping.
    Use low total (< PASS_TOTAL) so the total-based pass doesn't fire."""
    ws = _make_workspace(tmp_path)

    # One prior entry with total = 3.0 (low, below PASS_TOTAL).
    prior_dims = {d: 3 for d in DIMENSIONS}
    prior_history = [
        {"iteration": 1, "total": 3.0, "dimensions": prior_dims}
    ]
    write_json(ws / "review" / "mock_judge_scores.json", prior_history)

    # Judge returns same total (3.0) — not improving.
    llm = _StubbedLLM(dimensions=prior_dims)  # avg = 3.0 ≤ 3.0

    MockJudgeGateAgent(llm).run(ws)

    decision_raw = read_json(ws / "review" / "mock_judge_gate.json", {})
    assert decision_raw["status"] == "pass", (
        "Non-improving score should stop the loop."
    )


def test_history_accumulates_across_calls(tmp_path: Path) -> None:
    """Each call to run() appends one entry to mock_judge_scores.json."""
    ws = _make_workspace(tmp_path)

    # First call — low scores (will repair because total < PASS_TOTAL and dim < FLOOR).
    llm_low = _StubbedLLM(dimensions=_all_floor_except("figures", low_score=1))
    MockJudgeGateAgent(llm_low).run(ws)

    scores = read_json(ws / "review" / "mock_judge_scores.json", [])
    assert len(scores) == 1
    assert scores[0]["iteration"] == 1


# ---------------------------------------------------------------------------
# Wiring tests
# ---------------------------------------------------------------------------


def test_mock_judge_gate_in_gate_decision_files() -> None:
    assert "mock_judge_gate" in GATE_DECISION_FILES
    assert GATE_DECISION_FILES["mock_judge_gate"] == "review/mock_judge_gate.json"


def test_workflow_graph_edges_typesetting_through_mock_judge_gate() -> None:
    graph = build_default_workflow_graph()

    # New path: typesetting → mock_judge_gate → pre_submission_review
    assert graph.has_edge("typesetting", "mock_judge_gate"), (
        "Expected edge typesetting → mock_judge_gate"
    )
    assert graph.has_edge("mock_judge_gate", "pre_submission_review"), (
        "Expected edge mock_judge_gate → pre_submission_review"
    )

    # Old direct edge must NOT exist.
    assert not graph.has_edge("typesetting", "pre_submission_review"), (
        "Direct edge typesetting → pre_submission_review should have been removed."
    )


def test_mock_judge_gate_node_exists_in_graph() -> None:
    graph = build_default_workflow_graph()
    assert "mock_judge_gate" in graph.nodes


class _SequenceLLM:
    """Fake LLM returning a different RubricScore per call (drives multi-iter tests)."""

    def __init__(self, dim_seq: list[dict[str, int]]):
        self._seq = dim_seq
        self.calls = 0

    def generate(self, system: str, prompt: str, **kwargs: object) -> ProviderResult:
        dims = self._seq[min(self.calls, len(self._seq) - 1)]
        self.calls += 1
        payload = {
            "dimensions": dims,
            "comments": {d: "ok" for d in dims},
            "revision_suggestions": [],
        }
        return ProviderResult(content="```json\n" + json.dumps(payload) + "\n```", metadata={})


# ---------------------------------------------------------------------------
# Task A1: repair_directive.json tests
# ---------------------------------------------------------------------------


def test_repair_directive_written_on_needs_repair(tmp_path: Path) -> None:
    """needs_repair path: repair_directive.json must be written with correct fields."""
    ws = _make_workspace(tmp_path)
    llm = _StubbedLLM(
        dimensions=_all_floor_except("figures", low_score=1),
        revision_suggestions=["Add flow charts.", "Use colour coding.", "Add a legend."],
    )
    # Override comments to be non-trivial so we can assert on critique field.
    llm._dims_comments = {"figures": "The figures are too sparse and lack labelling."}

    agent = MockJudgeGateAgent(llm)
    outputs = agent.run(ws)

    directive_path = ws / "review" / "repair_directive.json"
    assert directive_path.exists(), "repair_directive.json must be written on needs_repair"

    from mcm_agent.utils.json_io import read_json
    directive = read_json(directive_path, {})

    assert directive["weak_dimension"] == "figures"
    assert directive["target_stage"] == "figure_planning"
    assert "critique" in directive
    assert "suggestions" in directive
    assert isinstance(directive["suggestions"], list)
    assert "review/repair_directive.json" in outputs


def test_repair_directive_removed_on_pass(tmp_path: Path) -> None:
    """pass path: a stale repair_directive.json must be deleted."""
    ws = _make_workspace(tmp_path)
    # Pre-create a stale directive file.
    directive_path = ws / "review" / "repair_directive.json"
    directive_path.parent.mkdir(parents=True, exist_ok=True)
    directive_path.write_text('{"stale": true}', encoding="utf-8")

    # High scores → natural pass.
    llm = _StubbedLLM(dimensions={d: 8 for d in DIMENSIONS})
    MockJudgeGateAgent(llm).run(ws)

    assert not directive_path.exists(), "stale repair_directive.json must be removed on pass"


def test_keep_best_ships_best_iteration_not_last(tmp_path: Path) -> None:
    """Keep-best: across noisy iterations (2.0 -> 3.0 -> 1.0), the workflow must ship
    the BEST iteration's paper (iter2), not the last (iter3, which regressed)."""
    ws = _make_workspace(tmp_path)
    intro = ws / "paper" / "sections" / "intro.tex"
    # score_consensus calls .score() `samples` times (default 3) per run(), so
    # each per-iteration dims entry must appear 3 times in the sequence.
    llm = _SequenceLLM(
        [
            {d: 2 for d in DIMENSIONS},  # iter1 sample 1
            {d: 2 for d in DIMENSIONS},  # iter1 sample 2
            {d: 2 for d in DIMENSIONS},  # iter1 sample 3  → avg total 2.0
            {d: 3 for d in DIMENSIONS},  # iter2 sample 1
            {d: 3 for d in DIMENSIONS},  # iter2 sample 2
            {d: 3 for d in DIMENSIONS},  # iter2 sample 3  → avg total 3.0  <- best
            {d: 1 for d in DIMENSIONS},  # iter3 sample 1
            {d: 1 for d in DIMENSIONS},  # iter3 sample 2
            {d: 1 for d in DIMENSIONS},  # iter3 sample 3  → avg total 1.0  → MAX_ITERS pass
        ]
    )
    agent = MockJudgeGateAgent(llm)
    for marker in ("ITER1", "ITER2", "ITER3"):
        intro.write_text(
            rf"\section{{Introduction}} {marker} with sensitivity analysis and validation.",
            encoding="utf-8",
        )
        agent.run(ws)

    # iter3 forced a pass (iteration >= MAX_ITERS) -> best (iter2) restored.
    assert "ITER2" in intro.read_text(encoding="utf-8")
    assert "ITER3" not in intro.read_text(encoding="utf-8")
    hist = read_json(ws / "review" / "mock_judge_scores.json", [])
    assert [round(e["total"], 1) for e in hist] == [2.0, 3.0, 1.0]
