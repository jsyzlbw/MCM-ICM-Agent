from pathlib import Path

from mcm_agent.agents.validation import ValidationAgent
from mcm_agent.core.events import EventLog
from mcm_agent.core.workspace import create_workspace
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
