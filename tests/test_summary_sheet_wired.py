"""Integration test: SummarySheetAgent must be invoked by PaperWriterAgent.run().

PQ6 built SummarySheetAgent and unit-tested it in isolation, and wired
_write_main_files to conditionally \\input summary_sheet.tex when the file
exists.  BUT PaperWriterAgent.run() never calls SummarySheetAgent.run(), so
a normal workflow run does NOT produce paper/summary_sheet.tex.

This test runs PaperWriterAgent.run() on a workspace that has the prerequisite
artifacts (model_spec, metrics, direction_lock, claim_plan) and asserts that
AFTER it runs:
  1. paper/summary_sheet.tex EXISTS
  2. paper/main.tex contains \\input{summary_sheet}

The test MUST fail before the wiring fix and PASS after.
"""
from __future__ import annotations

import json
from pathlib import Path


from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.model_spec import ModelSpec, SubproblemModel, write_model_spec
from mcm_agent.core.workspace import create_workspace


def _make_workspace(tmp_path: Path) -> Path:
    """Build a workspace with all artifacts PaperWriterAgent.run() needs.

    We use the claim-plan code path (paper/claim_plan.json present) because
    that is the real production path the workflow takes after ClaimPlanningAgent
    runs.
    """
    root = create_workspace(tmp_path / "ws").root

    # Language direction lock (required by confirmed_language)
    (root / "discussion").mkdir(parents=True, exist_ok=True)
    (root / "discussion" / "direction_lock.json").write_text(
        json.dumps({"language": "en", "selected_route": "regression"}),
        encoding="utf-8",
    )

    # ModelSpec (required by build_paper_context and SummarySheetAgent)
    spec = ModelSpec(
        version=1,
        problem_restatement="Estimate optimal wildfire resource allocation.",
        subproblems=[
            SubproblemModel(
                subproblem_id="SP1",
                title="Coverage Allocation",
                approach="constrained linear programming",
                variables=[],
                assumptions=["Homogeneous terrain"],
                equations=[],
                algorithm_steps=["Step 1: formulate LP", "Step 2: solve"],
                metrics=["coverage_rate"],
            )
        ],
    )
    write_model_spec(root, spec)

    # Metrics (real values — required by SummarySheetAgent)
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / "model_metrics.json").write_text(
        json.dumps({"coverage_rate": 0.87, "response_time_s": 42.0}),
        encoding="utf-8",
    )

    # Stub files that build_paper_context tries to read (gracefully handles missing,
    # but write them so coverage_rate shows up in paper context)
    (root / "results" / "model_route_summary.json").write_text(
        json.dumps({"selected_routes": ["constrained_lp"], "route_metrics": {}}),
        encoding="utf-8",
    )
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\nWildfire resource allocation.\n",
        encoding="utf-8",
    )
    (root / "discussion" / "confirmed_direction.md").write_text(
        "# Direction\nUse LP approach.\n",
        encoding="utf-8",
    )

    # Minimal claim plan (triggers the claim-plan path in PaperWriterAgent.run)
    paper_dir = root / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    claim_plan = [
        {
            "claim_id": "claim_model_route",
            "section": "paper/sections/model.tex",
            "claim_text": "We apply constrained LP to allocate resources.",
            "claim_type": "model_choice",
            "priority": "critical",
            "evidence_ids": ["ev_01"],
            "figure_ids": [],
            "source_ids": [],
            "status": "planned",
        },
        {
            "claim_id": "claim_results_primary",
            "section": "paper/sections/results.tex",
            "claim_text": "Coverage rate reaches 0.87.",
            "claim_type": "metric_result",
            "priority": "critical",
            "evidence_ids": ["ev_01"],
            "figure_ids": [],
            "source_ids": [],
            "status": "planned",
        },
    ]
    (paper_dir / "claim_plan.json").write_text(
        json.dumps(claim_plan), encoding="utf-8"
    )

    # Sections dir must exist (PaperWriterAgent creates it, but be safe)
    (paper_dir / "sections").mkdir(parents=True, exist_ok=True)

    # unresolved_issues.md must exist for the writer to append to it
    (root / "unresolved_issues.md").write_text("", encoding="utf-8")

    return root


def test_paper_writer_run_produces_summary_sheet(tmp_path: Path) -> None:
    """PaperWriterAgent.run() must create paper/summary_sheet.tex.

    This verifies the wiring: SummarySheetAgent must be called from within
    the run() method so the file is produced as part of normal paper writing.
    Without the wiring fix, this test fails because summary_sheet.tex is
    never written.
    """
    root = _make_workspace(tmp_path)

    PaperWriterAgent().run(root)  # no LLM — uses deterministic fallback

    summary_sheet = root / "paper" / "summary_sheet.tex"
    assert summary_sheet.exists(), (
        "paper/summary_sheet.tex was NOT created by PaperWriterAgent.run().\n"
        "SummarySheetAgent.run() must be called from within PaperWriterAgent.run().\n"
        "See .superpowers/sdd/pq6-wire-report.md for details."
    )


def test_paper_writer_run_main_tex_includes_summary_sheet(tmp_path: Path) -> None:
    """After PaperWriterAgent.run(), main.tex must \\input{summary_sheet}.

    _write_main_files conditionally includes the \\input only when
    summary_sheet.tex exists.  If SummarySheetAgent.run() is not called first,
    the file won't exist and the \\input will be absent.
    """
    root = _make_workspace(tmp_path)

    PaperWriterAgent().run(root)

    main_tex = root / "paper" / "main.tex"
    assert main_tex.exists(), "paper/main.tex was not produced by PaperWriterAgent.run()"

    content = main_tex.read_text(encoding="utf-8")
    assert "\\input{summary_sheet}" in content, (
        "main.tex does not contain \\input{summary_sheet}.\n"
        "SummarySheetAgent must run BEFORE _write_main_files so the file exists "
        "for the conditional include check.\n"
        f"main.tex content:\n{content}"
    )
