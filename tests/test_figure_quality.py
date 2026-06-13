from pathlib import Path

import pytest

from mcm_agent.agents.figure_quality import FigureQualityAgent
from mcm_agent.core.models import FigurePlanItem
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json, write_json


def test_figure_plan_item_tracks_claim_sources_and_evidence() -> None:
    item = FigurePlanItem(
        figure_id="fig_q1",
        purpose="show result trend",
        figure_type="data_plot",
        source_data=["results/problem1_results.csv"],
        output_formats=["pdf", "svg"],
        target_section="paper/sections/results.tex",
        caption_intent="Result trend.",
        claim_supported="The model output increases over observations.",
        source_ids=["web_001"],
        evidence_ids=["metric_row_count"],
    )

    assert item.claim_supported == "The model output increases over observations."
    assert item.source_ids == ["web_001"]
    assert item.evidence_ids == ["metric_row_count"]


def test_data_plot_plan_still_requires_vector_output() -> None:
    with pytest.raises(ValueError, match="data_plot figures require pdf or svg output"):
        FigurePlanItem(
            figure_id="fig_q1",
            purpose="show result trend",
            figure_type="data_plot",
            source_data=["results/problem1_results.csv"],
            output_formats=["png"],
            target_section="paper/sections/results.tex",
            caption_intent="Result trend.",
        )


def test_figure_quality_agent_passes_complete_data_figure(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_complete_figure_workspace(workspace.root)

    FigureQualityAgent().run(workspace.root)

    report = (workspace.root / "review" / "figure_quality_report.md").read_text(encoding="utf-8")
    gate = read_json(workspace.root / "review" / "figure_gate.json", {})
    assert "Blocking issues: 0" in report
    assert gate["status"] == "pass"


def test_figure_quality_agent_fails_missing_trace_and_vector_outputs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    source = workspace.root / "results" / "problem1_results.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    write_json(
        workspace.root / "figures" / "figure_plan.json",
        [
            {
                "figure_id": "fig_q1",
                "purpose": "show result trend",
                "figure_type": "data_plot",
                "source_data": ["results/problem1_results.csv"],
                "output_formats": ["pdf"],
                "target_section": "",
                "caption_intent": "",
                "evidence_ids": [],
                "source_ids": [],
            }
        ],
    )
    png = workspace.root / "figures" / "fig_q1.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_text("not a real image", encoding="utf-8")
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [
            {
                "figure_id": "fig_q1",
                "type": "data_plot",
                "tool": "matplotlib",
                "source_file": "figures/source/missing.py",
                "outputs": ["figures/fig_q1.png"],
                "used_in": [],
                "status": "approved",
            }
        ],
    )

    FigureQualityAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "figure_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["repair_stage"] == "figure_planning"
    assert any("no PDF/SVG output" in issue for issue in gate["blocking_findings"])
    assert any("missing caption intent" in issue for issue in gate["blocking_findings"])
    assert any("missing evidence_ids" in issue for issue in gate["blocking_findings"])


def _write_complete_figure_workspace(workspace_root: Path) -> None:
    result = workspace_root / "results" / "problem1_results.csv"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    script = workspace_root / "figures" / "source" / "fig_q1.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# plot script\n", encoding="utf-8")
    for suffix in ["pdf", "svg"]:
        (workspace_root / "figures" / f"fig_q1.{suffix}").write_text("figure", encoding="utf-8")
    write_json(
        workspace_root / "figures" / "figure_plan.json",
        [
            {
                "figure_id": "fig_q1",
                "purpose": "show result trend",
                "figure_type": "data_plot",
                "source_data": ["results/problem1_results.csv"],
                "output_formats": ["pdf", "svg"],
                "target_section": "paper/sections/results.tex",
                "caption_intent": "Result trend.",
                "claim_supported": "The model output increases over observations.",
                "source_ids": ["web_001"],
                "evidence_ids": ["metric_row_count"],
            }
        ],
    )
    write_json(
        workspace_root / "figures" / "figure_registry.json",
        [
            {
                "figure_id": "fig_q1",
                "type": "data_plot",
                "tool": "matplotlib",
                "source_file": "figures/source/fig_q1.py",
                "outputs": ["figures/fig_q1.pdf", "figures/fig_q1.svg"],
                "used_in": ["paper/sections/results.tex"],
                "status": "approved",
            }
        ],
    )
