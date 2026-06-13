from pathlib import Path

from mcm_agent.agents.extraction import DocumentExtractionAgent
from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.validation import ValidationAgent
from mcm_agent.agents.visualization import VisualizationAgent
from mcm_agent.core.gate_decision import GateDecision
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.mineru import ParsedDocument
from mcm_agent.utils.json_io import read_json, write_json


class EmptyMinerUProvider:
    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        markdown_path.write_text("", encoding="utf-8")
        json_path.write_text("{}", encoding="utf-8")
        return ParsedDocument(markdown_path=str(markdown_path), json_path=str(json_path))


def test_gate_decision_records_status_and_findings() -> None:
    decision = GateDecision(
        gate_id="validation_gate",
        status="fail",
        failure_reason="bad_data",
        blocking_findings=["Missing evidence."],
    )

    assert decision.passed is False
    assert decision.blocking_findings == ["Missing evidence."]


def test_extraction_agent_writes_failed_gate_for_empty_parse(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem = workspace.root / "input" / "problem.pdf"
    problem.write_bytes(b"%PDF fake")

    DocumentExtractionAgent(EmptyMinerUProvider()).run(workspace.root)

    decision = read_json(workspace.root / "review" / "extraction_gate.json", {})
    assert decision["status"] == "fail"
    assert decision["failure_reason"] == "missing_problem_text"


def test_validation_agent_writes_failed_gate_when_metric_evidence_missing(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(workspace.root / "results" / "model_metrics.json", {"row_count": 2})
    write_json(workspace.root / "results" / "evidence_registry.json", [])

    ValidationAgent().run(workspace.root)

    decision = read_json(workspace.root / "review" / "validation_gate.json", {})
    assert decision["status"] == "fail"
    assert decision["failure_reason"] == "bad_results"
    assert decision["repair_stage"] == "solver_coder"


def test_visualization_agent_writes_figure_gate(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    results = workspace.root / "results" / "problem1_results.csv"
    results.write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "metric_row_count"}],
    )
    write_json(
        workspace.root / "figures" / "figure_plan.json",
        [
            {
                "figure_id": "fig_q1",
                "purpose": "show result",
                "figure_type": "data_plot",
                "source_data": ["results/problem1_results.csv"],
                "generation_script": "figures/source/fig_q1.py",
                "output_formats": ["pdf", "svg"],
                "target_section": "paper/sections/results.tex",
                "caption_intent": "Result trend.",
                "evidence_ids": ["metric_row_count"],
            }
        ],
    )

    VisualizationAgent().run(workspace.root)

    decision = read_json(workspace.root / "review" / "figure_gate.json", {})
    assert decision["status"] == "pass"


def test_reviewer_writes_final_gate_for_blocking_source_issue(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "data" / "source_registry.json",
        [
            {
                "source_id": "web_001",
                "title": "Official source",
                "url": "https://data.gov/example",
                "accessed_at": "2026-06-13T12:00:00Z",
                "license": "unknown",
                "provider": "FakeSearch",
                "source_rank": "official",
                "used_for": "external data discovery",
                "citation": "Official source",
                "local_path": "data/external/source_001.md",
            }
        ],
    )

    ReviewerAgent().run(workspace.root)

    decision = read_json(workspace.root / "review" / "final_gate.json", {})
    assert decision["status"] == "fail"
    assert decision["failure_reason"] == "bad_data"
    assert decision["repair_stage"] == "search_data"
