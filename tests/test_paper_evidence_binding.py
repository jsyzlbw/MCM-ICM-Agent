from pathlib import Path

from mcm_agent.agents.paper_evidence import PaperEvidenceBindingAgent
from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


def test_paper_evidence_binding_agent_records_traceable_claims(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\n"
        "The row count claim is supported by evidence_id=ev_001, "
        "figure_id=fig_001, and source_id=web_001.\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_001", "verified": True}],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_001", "status": "approved"}],
    )
    write_json(
        workspace.root / "data" / "source_registry.json",
        [{"source_id": "web_001", "source_rank": "official"}],
    )

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    report = (workspace.root / "review" / "paper_evidence_report.md").read_text(
        encoding="utf-8"
    )
    assert bindings[0]["section"] == "paper/sections/results.tex"
    assert bindings[0]["evidence_ids"] == ["ev_001"]
    assert bindings[0]["figure_ids"] == ["fig_001"]
    assert bindings[0]["source_ids"] == ["web_001"]
    assert bindings[0]["status"] == "pass"
    assert "Missing bindings: 0" in report


def test_reviewer_blocks_paper_claim_without_evidence_binding(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\nThe model improves the final policy score.\n",
        encoding="utf-8",
    )
    write_json(workspace.root / "data" / "source_registry.json", [])
    write_json(workspace.root / "data" / "data_lineage.json", [])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    (workspace.root / "paper" / "references.bib").write_text("", encoding="utf-8")

    PaperEvidenceBindingAgent().run(workspace.root)
    ReviewerAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "final_gate.json", {})
    assert gate["status"] == "fail"
    assert gate["failure_reason"] == "bad_writing"
    assert any("Paper claims are missing evidence bindings" in item for item in gate["blocking_findings"])


def test_paper_writer_adds_trace_tokens_to_model_sensitivity_and_conclusion(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation"],
            "route_metrics": {
                "priority_score_mean": {
                    "route_id": "multi_criteria_evaluation",
                    "value": 0.6,
                },
            },
        },
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "metric_priority_score_mean"}],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_priority_ranking"}],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    PaperWriterAgent().run(workspace.root)

    section_dir = workspace.root / "paper" / "sections"
    for section_name in ("model.tex", "sensitivity.tex", "conclusion.tex"):
        text = (section_dir / section_name).read_text(encoding="utf-8")
        assert "% evidence_id=metric_priority_score_mean" in text
        assert "% figure_id=fig_priority_ranking" in text
        assert "% source_id=web_001" in text


def test_paper_evidence_binding_requires_all_claim_sections_to_be_traceable(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\nThe result is supported by evidence_id=ev_001.\n",
        encoding="utf-8",
    )
    for section_name in ("model.tex", "sensitivity.tex", "conclusion.tex"):
        (section_dir / section_name).write_text(
            "\\section{Claim Section}\nThis section makes contest-paper claims.\n",
            encoding="utf-8",
        )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    status_by_section = {
        Path(str(binding["section"])).name: binding["status"] for binding in bindings
    }
    assert status_by_section["results.tex"] == "pass"
    assert status_by_section["model.tex"] == "fail"
    assert status_by_section["sensitivity.tex"] == "fail"
    assert status_by_section["conclusion.tex"] == "fail"


def test_paper_evidence_binding_records_claim_level_bindings(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\n"
        "The primary metric is stable.\n"
        "% claim_id=claim_results_primary evidence_id=ev_001 figure_id=fig_001 source_id=web_001\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_001"}],
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [{"figure_id": "fig_001"}])
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    assert bindings[0]["status"] == "pass"
    assert bindings[0]["claim_bindings"] == [
        {
            "claim_id": "claim_results_primary",
            "evidence_ids": ["ev_001"],
            "figure_ids": ["fig_001"],
            "source_ids": ["web_001"],
            "missing_bindings": [],
            "status": "pass",
        }
    ]
    report = (workspace.root / "review" / "paper_evidence_report.md").read_text(
        encoding="utf-8"
    )
    assert "## Claim Bindings" in report
    assert "`claim_results_primary`: pass" in report


def test_paper_evidence_binding_fails_unbound_claim_level_marker(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "model.tex").write_text(
        "\\section{Model}\n"
        "The chosen model is feasible.\n"
        "% claim_id=claim_model_choice evidence_id=missing figure_id=fig_unknown\n",
        encoding="utf-8",
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    assert bindings[0]["status"] == "fail"
    assert bindings[0]["claim_bindings"][0]["status"] == "fail"
    assert any(
        "Claim has no evidence, figure, or source binding" in item
        for item in bindings[0]["claim_bindings"][0]["missing_bindings"]
    )
    assert any(
        "Unknown figure ids: fig_unknown" in item
        for item in bindings[0]["claim_bindings"][0]["missing_bindings"]
    )


def test_paper_writer_emits_claim_level_trace_tokens(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation"],
            "route_metrics": {
                "priority_score_mean": {
                    "route_id": "multi_criteria_evaluation",
                    "value": 0.6,
                },
            },
        },
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "metric_priority_score_mean"}],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_priority_ranking"}],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    PaperWriterAgent().run(workspace.root)

    section_dir = workspace.root / "paper" / "sections"
    expected = {
        "model.tex": "% claim_id=claim_model_route",
        "results.tex": "% claim_id=claim_results_primary",
        "sensitivity.tex": "% claim_id=claim_sensitivity_baseline",
        "conclusion.tex": "% claim_id=claim_conclusion_traceability",
    }
    for section_name, claim_token in expected.items():
        text = (section_dir / section_name).read_text(encoding="utf-8")
        assert claim_token in text
        assert "evidence_id=metric_priority_score_mean" in text
        assert "figure_id=fig_priority_ranking" in text
        assert "source_id=web_001" in text


def test_paper_writer_uses_claim_plan_when_available(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_planned_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The planned result is supported by the registered metric.",
                "claim_type": "metric_result",
                "evidence_ids": ["ev_001"],
                "figure_ids": ["fig_001"],
                "source_ids": ["web_001"],
                "priority": "critical",
                "status": "planned",
                "unresolved_reason": "",
            }
        ],
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "figures" / "figure_registry.json", [{"figure_id": "fig_001"}])
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    PaperWriterAgent().run(workspace.root)

    results = (workspace.root / "paper" / "sections" / "results.tex").read_text(
        encoding="utf-8"
    )
    assert "The planned result is supported by the registered metric." in results
    assert (
        "% claim_id=claim_planned_result evidence_id=ev_001 "
        "figure_id=fig_001 source_id=web_001"
    ) in results


def test_paper_writer_records_unresolved_planned_claims(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_unresolved_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The missing metric cannot be reported.",
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

    PaperWriterAgent().run(workspace.root)

    unresolved = (workspace.root / "unresolved_issues.md").read_text(encoding="utf-8")
    results = (workspace.root / "paper" / "sections" / "results.tex").read_text(
        encoding="utf-8"
    )
    assert "claim_unresolved_result" in unresolved
    assert "Solver evidence is missing." in unresolved
    assert (
        "% claim_id=claim_unresolved_result evidence_id=missing "
        "figure_id=missing source_id=missing"
    ) in results


def test_paper_evidence_binding_fails_missing_planned_critical_claim(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\nNo planned claim marker.\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_planned_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The planned result must be written.",
                "claim_type": "metric_result",
                "evidence_ids": ["ev_001"],
                "figure_ids": [],
                "source_ids": [],
                "priority": "critical",
                "status": "planned",
                "unresolved_reason": "",
            }
        ],
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_001"}])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    report = (workspace.root / "review" / "paper_evidence_report.md").read_text(
        encoding="utf-8"
    )
    assert bindings[0]["status"] == "fail"
    assert "Omitted planned claims: claim_planned_result" in report


def test_paper_evidence_binding_rejects_bindings_outside_plan(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    section_dir = workspace.root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    (section_dir / "results.tex").write_text(
        "\\section{Results}\n"
        "% claim_id=claim_planned_result evidence_id=ev_wrong\n",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_planned_result",
                "section": "paper/sections/results.tex",
                "claim_text": "The planned result must use ev_001.",
                "claim_type": "metric_result",
                "evidence_ids": ["ev_001"],
                "figure_ids": [],
                "source_ids": [],
                "priority": "major",
                "status": "planned",
                "unresolved_reason": "",
            }
        ],
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_001"}, {"evidence_id": "ev_wrong"}],
    )
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    PaperEvidenceBindingAgent().run(workspace.root)

    bindings = read_json(workspace.root / "review" / "paper_evidence_bindings.json", [])
    assert bindings[0]["status"] == "fail"
    assert any(
        "Evidence ids outside claim plan: ev_wrong" in item
        for item in bindings[0]["missing_bindings"]
    )
