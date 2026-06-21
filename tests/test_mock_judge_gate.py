"""Tests for MockJudgeGateAgent (O6: self-eval closed loop).

All tests are offline and deterministic — no real LLM or kernel is used.
We stub the LLM the same way test_mock_judge.py does (_JudgeLLM pattern).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcm_agent.agents.mock_judge import DIMENSIONS
from mcm_agent.agents.mock_judge_gate import MAX_ITERS, PASS_TOTAL, DIM_TO_STAGE, MockJudgeGateAgent
from mcm_agent.core.gate_decision import GateDecision
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


def test_passes_at_max_iters_even_if_low(tmp_path: Path) -> None:
    """TERMINATION GUARD: pre-seed MAX_ITERS-1 prior low entries so the next
    call is iteration MAX_ITERS, which must force a pass."""
    ws = _make_workspace(tmp_path)

    # Pre-seed history with MAX_ITERS-1 entries — all low scores (avg 2.0, total < PASS_TOTAL).
    prior_history = [
        {"iteration": i + 1, "total": 2.0, "dimensions": {d: 2 for d in DIMENSIONS}}
        for i in range(MAX_ITERS - 1)
    ]
    # Use increasing totals so the "not improving" guard doesn't fire early.
    for i, entry in enumerate(prior_history):
        entry["total"] = float(i + 2)
    write_json(ws / "review" / "mock_judge_scores.json", prior_history)

    # Judge returns a low paper (would normally trigger repair).
    # Total = 3.0 > last entry's total, so not-improving guard won't fire.
    llm = _StubbedLLM(dimensions={d: 3 for d in DIMENSIONS})

    MockJudgeGateAgent(llm).run(ws)

    decision_raw = read_json(ws / "review" / "mock_judge_gate.json", {})
    assert decision_raw["status"] == "pass", (
        "Gate must pass at MAX_ITERS to prevent infinite loops."
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
