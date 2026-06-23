"""PQ1: tests that rendered figures are embedded into LaTeX sections."""
from __future__ import annotations

from pathlib import Path


from mcm_agent.agents.figure_quality import FigureQualityAgent
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_figure_workspace(workspace_root: Path) -> None:
    """Populate the minimum workspace so writer.run() produces sections with an
    embedded figure from figure_registry.json."""
    # Data source used by evidence / sources (not strictly required but writer
    # reads these gracefully if absent).
    results_dir = workspace_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "evidence_registry.json").write_text("[]", encoding="utf-8")
    (workspace_root / "data").mkdir(parents=True, exist_ok=True)
    (workspace_root / "data" / "source_registry.json").write_text("[]", encoding="utf-8")
    (results_dir / "model_route_summary.json").write_text("{}", encoding="utf-8")

    # A real figure file on disk (the writer should reference it by id).
    figures_dir = workspace_root / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    (figures_dir / "fig_result_trend.pdf").write_text("%PDF-placeholder", encoding="utf-8")

    # The figure registry: used_in points to the results section.
    write_json(
        figures_dir / "figure_registry.json",
        [
            {
                "figure_id": "fig_result_trend",
                "type": "data_plot",
                "tool": "matplotlib",
                "source_file": "figures/source/fig_result_trend_plot.py",
                "outputs": ["figures/fig_result_trend.pdf"],
                "used_in": ["paper/sections/results.tex"],
                "status": "approved",
                "caption_intent": "Baseline result trend for Problem 1.",
                "claim_supported": "Baseline result trend.",
                "source_data": [],
                "source_ids": [],
                "evidence_ids": [],
            }
        ],
    )

    # No claim_plan.json → writer falls back to the fallback path that also
    # reads figure_registry.json.
    (workspace_root / "paper").mkdir(parents=True, exist_ok=True)
    (workspace_root / "unresolved_issues.md").write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: writer embeds \includegraphics into the produced .tex
# ---------------------------------------------------------------------------

def test_writer_embeds_figure_includegraphics(tmp_path: Path) -> None:
    """PaperWriterAgent must embed \\includegraphics for each registry figure
    whose used_in matches a section being written."""
    workspace = create_workspace(tmp_path / "run_001")
    _make_figure_workspace(workspace.root)

    PaperWriterAgent().run(workspace.root)

    # The results section should contain the figure float.
    results_tex = (workspace.root / "paper" / "sections" / "results.tex").read_text(
        encoding="utf-8"
    )
    assert "\\includegraphics" in results_tex, (
        "Expected \\includegraphics in results.tex but found none.\n"
        f"results.tex content:\n{results_tex}"
    )
    assert "fig_result_trend" in results_tex, (
        "Expected figure id 'fig_result_trend' in results.tex.\n"
        f"results.tex content:\n{results_tex}"
    )
    assert "\\caption" in results_tex, (
        "Expected \\caption in results.tex.\n"
        f"results.tex content:\n{results_tex}"
    )
    assert "\\label{fig:fig_result_trend}" in results_tex, (
        "Expected \\label{fig:fig_result_trend} in results.tex.\n"
        f"results.tex content:\n{results_tex}"
    )
    assert "Baseline result trend for Problem 1." in results_tex, (
        "Expected caption text in results.tex.\n"
        f"results.tex content:\n{results_tex}"
    )


def test_main_tex_has_graphicspath(tmp_path: Path) -> None:
    """main.tex must include \\graphicspath so the PDF compiler can find figures."""
    workspace = create_workspace(tmp_path / "run_001")
    _make_figure_workspace(workspace.root)

    PaperWriterAgent().run(workspace.root)

    main_tex = (workspace.root / "paper" / "main.tex").read_text(encoding="utf-8")
    assert "\\graphicspath" in main_tex, (
        "Expected \\graphicspath in main.tex.\n"
        f"main.tex content:\n{main_tex}"
    )


# ---------------------------------------------------------------------------
# Test 2: FigureQualityAgent flags blocking finding when figures not embedded
# ---------------------------------------------------------------------------

def _make_unembedded_figure_workspace(workspace_root: Path) -> None:
    """Workspace where figure_registry says a figure should go into results.tex
    but the written results.tex contains no \\includegraphics."""
    figures_dir = workspace_root / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    (figures_dir / "fig_result_trend.pdf").write_text("%PDF", encoding="utf-8")

    source_dir = figures_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "fig_result_trend_plot.py").write_text("# script\n", encoding="utf-8")

    write_json(
        figures_dir / "figure_plan.json",
        [
            {
                "figure_id": "fig_result_trend",
                "purpose": "show result trend",
                "figure_type": "data_plot",
                "source_data": ["results/problem1_results.csv"],
                "output_formats": ["pdf"],
                "target_section": "paper/sections/results.tex",
                "caption_intent": "Baseline result trend.",
                "claim_supported": "The model output increases.",
                "source_ids": [],
                "evidence_ids": ["ev_001"],
            }
        ],
    )
    write_json(
        figures_dir / "figure_registry.json",
        [
            {
                "figure_id": "fig_result_trend",
                "type": "data_plot",
                "tool": "matplotlib",
                "source_file": "figures/source/fig_result_trend_plot.py",
                "outputs": ["figures/fig_result_trend.pdf"],
                "used_in": ["paper/sections/results.tex"],
                "status": "approved",
                "caption_intent": "Baseline result trend.",
                "claim_supported": "The model output increases.",
                "source_data": [],
                "source_ids": [],
                "evidence_ids": ["ev_001"],
            }
        ],
    )

    # Write a results section WITHOUT any \includegraphics.
    paper_sections = workspace_root / "paper" / "sections"
    paper_sections.mkdir(parents=True, exist_ok=True)
    (paper_sections / "results.tex").write_text(
        "\\section{Results}\nSome text without any figure embedding.\n",
        encoding="utf-8",
    )

    # Also need a results CSV so _plan_issues doesn't fail on missing source.
    results_dir = workspace_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "problem1_results.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    (workspace_root / "review").mkdir(parents=True, exist_ok=True)


def test_figure_quality_flags_unembedded_figure(tmp_path: Path) -> None:
    """FigureQualityAgent must record a blocking finding when a registered
    figure exists but is NOT embedded (no \\includegraphics) in its target section."""
    workspace = create_workspace(tmp_path / "run_001")
    _make_unembedded_figure_workspace(workspace.root)

    FigureQualityAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "figure_gate.json", {})
    assert gate["status"] == "fail", (
        "Expected gate to fail when figure is not embedded in LaTeX.\n"
        f"gate: {gate}"
    )
    findings = gate.get("blocking_findings", [])
    assert any("not embedded" in f or "embed" in f.lower() for f in findings), (
        "Expected an embedding-related blocking finding.\n"
        f"findings: {findings}"
    )
