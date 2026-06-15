from pathlib import Path

from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.revision import RevisionAgent
from mcm_agent.core.events import EventLog
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


def _write_complete_paper_sections(workspace_root: Path) -> None:
    section_dir = workspace_root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "abstract.tex",
        "introduction.tex",
        "assumptions.tex",
        "model.tex",
        "results.tex",
        "sensitivity.tex",
        "conclusion.tex",
    ]:
        (section_dir / name).write_text(
            "\\section{X}\n"
            "Claim text.\n"
            "% claim_id=claim_x evidence_id=ev_001 figure_id=missing source_id=missing\n",
            encoding="utf-8",
        )


def test_reviewer_writes_reports_and_passes_clean_workspace(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "paper" / "main.tex").write_text("\\begin{document}x\\end{document}")
    (workspace.root / "paper" / "compile_log.txt").write_text("ok", encoding="utf-8")
    (workspace.root / "review" / "fact_regression_report.md").write_text(
        "# Fact Regression Report\n\n- No fact regression detected.",
        encoding="utf-8",
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    _write_complete_paper_sections(workspace.root)

    ReviewerAgent().run(workspace.root)

    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert (workspace.root / "review" / "reviewer_report.md").exists()
    assert (workspace.root / "review" / "source_audit_report.md").exists()
    assert events[-1].event_type == "paper.review.passed"


def test_reviewer_writes_paper_quality_scores(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_complete_paper_sections(workspace.root)
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "review" / "paper_evidence_bindings.json", [])

    ReviewerAgent().run(workspace.root)

    scores = read_json(workspace.root / "review" / "paper_quality_scores.json", {})
    assert scores["section_completeness"] == 1.0
    assert scores["claim_trace_density"] > 0
    assert scores["status"] == "pass"


def test_reviewer_blocks_incomplete_paper_sections(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text("\\section{Results}\nOnly results.\n", encoding="utf-8")

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    scores = read_json(workspace.root / "review" / "paper_quality_scores.json", {})
    assert scores["status"] == "fail"
    assert gate["status"] == "fail"
    assert gate["repair_stage"] == "paper_writer"
    assert "Paper section completeness is too low." in gate["blocking_findings"]


def test_reviewer_routes_typesetting_quality_failure_to_typesetting(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    _write_complete_paper_sections(workspace.root)
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    write_json(
        workspace.root / "review" / "typesetting_quality.json",
        {
            "status": "fail",
            "blocking_findings": ["LaTeX compile error: Undefined control sequence."],
            "repair_stage": "typesetting",
            "issue_types": ["compile_error"],
            "issues": [],
            "page_count": None,
        },
    )

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "format_issue"
    assert gate["repair_stage"] == "typesetting"


def test_reviewer_fails_with_unresolved_placeholder(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "unresolved_issues.md").write_text("[[UNRESOLVED:\n]]")

    ReviewerAgent().run(workspace.root)

    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert events[-1].event_type == "paper.review.failed"


def test_reviewer_blocks_unbound_external_data_source(tmp_path: Path) -> None:
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
    write_json(workspace.root / "data" / "data_lineage.json", [])

    ReviewerAgent().run(workspace.root)

    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    report = (workspace.root / "review" / "source_audit_report.md").read_text(
        encoding="utf-8"
    )
    assert events[-1].event_type == "paper.review.failed"
    assert "web_001" in report
    assert "Unbound external data sources" in report


def test_reviewer_routes_omitted_planned_claims_to_writer(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "review" / "paper_evidence_bindings.json",
        [
            {
                "section": "paper/sections/results.tex",
                "status": "fail",
                "missing_bindings": ["Omitted planned claims: claim_planned_result"],
                "claim_bindings": [],
            }
        ],
    )

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "bad_writing"
    assert gate["repair_stage"] == "paper_writer"


def test_reviewer_routes_unresolved_critical_claims_to_solver(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_unresolved_metric",
                "section": "paper/sections/results.tex",
                "claim_text": "The missing metric is required for the result.",
                "claim_type": "metric_result",
                "evidence_ids": [],
                "figure_ids": [],
                "source_ids": [],
                "priority": "critical",
                "status": "unresolved",
                "unresolved_reason": "Solver evidence is missing.",
            }
        ],
    )
    write_json(workspace.root / "review" / "paper_evidence_bindings.json", [])

    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "bad_results"
    assert gate["repair_stage"] == "solver_coder"
    assert any(
        "Critical planned claims remain unresolved" in item
        for item in gate["blocking_findings"]
    )


def test_revision_marks_artifacts_stale_for_result_request(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    registry = ArtifactRegistry(workspace.root / "artifact_registry.json")
    registry.add(
        ArtifactRecord(
            artifact_id="figure_v1",
            type="figure",
            path="figures/figure.pdf",
            producer="VisualizationAgent",
            depends_on=["model_decision_v1"],
            status=ArtifactStatus.APPROVED,
            created_at="2026-06-13T12:00:00Z",
        )
    )

    RevisionAgent().apply_revision_request(workspace.root, "Please rerun the model results.")

    assert (workspace.root / "review" / "revision_requests.md").exists()
    assert registry.get("figure_v1").status == ArtifactStatus.STALE
