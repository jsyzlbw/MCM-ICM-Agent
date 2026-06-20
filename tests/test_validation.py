from pathlib import Path

from mcm_agent.agents.validation import ValidationAgent
from mcm_agent.core.events import EventLog
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


def test_validation_passes_with_metric_evidence(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(workspace.root / "results" / "model_metrics.json", {"row_count": 3})
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_row_count",
                "claim": "Metric row_count equals 3.",
                "value": 3,
                "source_type": "code_output",
                "source_path": "results/model_metrics.json",
                "generated_by": "code/problem1.py",
                "used_in": [],
                "verified": True,
            }
        ],
    )

    ValidationAgent().run(workspace.root)

    report = (workspace.root / "reports" / "validation_report.md").read_text(encoding="utf-8")
    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert "## Blocking Issues" in report
    assert events[-1].event_type == "validation.passed"


def test_validation_fails_when_metric_evidence_missing(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(workspace.root / "results" / "model_metrics.json", {"row_count": 3})
    write_json(workspace.root / "results" / "evidence_registry.json", [])

    ValidationAgent().run(workspace.root)

    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert events[-1].event_type == "validation.failed"


def test_validation_fails_on_solver_binding_report_failure(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(workspace.root / "results" / "model_metrics.json", {})
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(
        workspace.root / "results" / "solver_binding_report.json",
        {
            "status": "fail",
            "missing_bindings": ["network_flow_graph.source_column"],
            "details": [],
        },
    )

    ValidationAgent().run(workspace.root)

    decision = read_json(workspace.root / "review" / "validation_gate.json", {})
    assert decision["status"] == "fail"
    assert decision["failure_reason"] == "weak_model"
    assert "network_flow_graph.source_column" in decision["blocking_findings"][0]


def test_validation_preserves_and_reports_real_sensitivity(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_sens")
    write_json(workspace.root / "results" / "model_metrics.json", {})
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    (workspace.root / "results" / "sensitivity_analysis.csv").write_text(
        "parameter,value,elimination_consistency_rate\n"
        "judge_weight,0.4,0.71\njudge_weight,0.6,0.66\n",
        encoding="utf-8",
    )

    ValidationAgent().run(workspace.root)

    sens = (workspace.root / "results" / "sensitivity_analysis.csv").read_text(encoding="utf-8")
    assert "judge_weight" in sens  # solver-produced sensitivity is NOT clobbered
    report = (workspace.root / "reports" / "validation_report.md").read_text(encoding="utf-8")
    assert "judge_weight" in report  # real sensitivity is reported
    assert "Baseline sensitivity file generated" not in report


def test_validation_notes_missing_sensitivity_without_fake_row(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_nosens")
    write_json(workspace.root / "results" / "model_metrics.json", {})
    write_json(workspace.root / "results" / "evidence_registry.json", [])

    ValidationAgent().run(workspace.root)

    sens = (workspace.root / "results" / "sensitivity_analysis.csv").read_text(encoding="utf-8")
    assert "baseline,0,0" not in sens  # no fabricated sensitivity row


def test_validation_routes_missing_solver_bindings_to_modeling_when_spec_is_wrong(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(workspace.root / "results" / "model_metrics.json", {"row_count": 2})
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "metric_row_count", "source_path": "results/model_metrics.json"}],
    )
    write_json(
        workspace.root / "results" / "solver_binding_report.json",
        {
            "status": "fail",
            "missing_bindings": [
                "network_flow_graph.source_column",
                "network_flow_graph.target_column",
            ],
        },
    )

    ValidationAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "validation_gate.json", {})
    assert gate["failure_reason"] == "weak_model"
    assert gate["repair_stage"] == "modeling_council"
