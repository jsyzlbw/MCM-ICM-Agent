from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcm_agent.core.events import EventLog
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus, EventRecord
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


NOW = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)


def test_create_workspace_initializes_required_files(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    required = [
        "task_state.json",
        "artifact_registry.json",
        "workflow_topology.json",
        "event_log.jsonl",
        "unresolved_issues.md",
        "discussion/data_questions.json",
        "data/source_registry.json",
        "data/data_lineage.json",
        "data/citation_candidates.json",
        "data/retrieval_log.jsonl",
        "results/evidence_registry.json",
        "figures/figure_plan.json",
        "figures/figure_registry.json",
        "review/methodology_checklist_report.md",
        "review/humanization_diff.md",
        "review/fact_regression_report.md",
    ]

    for relative_path in required:
        assert (workspace.root / relative_path).exists(), relative_path

    topology = read_json(workspace.root / "workflow_topology.json", {})
    assert "data_feasibility_scout" in topology["nodes"]
    assert {
        "from_node": "problem_understanding",
        "to_node": "data_feasibility_scout",
        "condition": "pass",
    } in topology["edges"]
    assert {
        "from_node": "user_discussion",
        "to_node": "data_feasibility_scout",
        "condition": "new_data_need",
    } in topology["edges"]


def test_artifact_registry_add_get_and_update(tmp_path: Path) -> None:
    registry = ArtifactRegistry(tmp_path / "artifact_registry.json")
    record = ArtifactRecord(
        artifact_id="a1",
        type="report",
        path="reports/a1.md",
        producer="TestAgent",
        created_at=NOW,
    )

    registry.add(record)
    registry.update_status("a1", ArtifactStatus.APPROVED)

    assert registry.get("a1").status == ArtifactStatus.APPROVED


def test_artifact_registry_rejects_duplicate_ids(tmp_path: Path) -> None:
    registry = ArtifactRegistry(tmp_path / "artifact_registry.json")
    record = ArtifactRecord(
        artifact_id="a1",
        type="report",
        path="reports/a1.md",
        producer="TestAgent",
        created_at=NOW,
    )

    registry.add(record)

    with pytest.raises(ValueError, match="artifact already exists: a1"):
        registry.add(record)


def test_artifact_registry_marks_dependents_stale(tmp_path: Path) -> None:
    registry = ArtifactRegistry(tmp_path / "artifact_registry.json")
    registry.add(
        ArtifactRecord(
            artifact_id="source",
            type="source",
            path="reports/source.md",
            producer="A",
            status=ArtifactStatus.APPROVED,
            created_at=NOW,
        )
    )
    registry.add(
        ArtifactRecord(
            artifact_id="child",
            type="child",
            path="reports/child.md",
            producer="B",
            depends_on=["source"],
            status=ArtifactStatus.APPROVED,
            created_at=NOW,
        )
    )

    marked = registry.mark_dependents_stale("source")

    assert marked == ["child"]
    assert registry.get("child").status == ArtifactStatus.STALE


def test_event_log_round_trips_events(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "event_log.jsonl")
    log.append(
        EventRecord(
            event_id="event_001",
            event_type="input.received",
            payload={"artifact_ids": ["input_manifest_v1"]},
            created_at=NOW,
            source="test",
        )
    )

    events = log.read_all()

    assert len(events) == 1
    assert events[0].event_type == "input.received"


def test_event_log_reports_invalid_line_number(tmp_path: Path) -> None:
    path = tmp_path / "event_log.jsonl"
    path.write_text("\nnot-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSONL at line 2"):
        EventLog(path).read_all()
