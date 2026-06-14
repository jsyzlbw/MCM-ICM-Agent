from pathlib import Path

from mcm_agent.agents.paper_evidence import PaperEvidenceBindingAgent
from mcm_agent.agents.reviewer import ReviewerAgent
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
