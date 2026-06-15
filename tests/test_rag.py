from pathlib import Path

from mcm_agent.agents.rag import MethodologyRAGAgent, MethodologyStore
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


def test_methodology_store_searches_figure_design(tmp_path: Path) -> None:
    store = MethodologyStore(tmp_path / "rag.db")
    store.initialize()
    store.add_document(
        "fixture",
        "Figure Designer",
        "Figure design requires data source tracking and experimental results.",
    )

    hits = store.search("figure design", limit=1)

    assert hits[0].title == "Figure Designer"


def test_methodology_rag_agent_generates_checklists(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "figure-designer"
    skill_dir.mkdir(parents=True)
    fixture = Path(__file__).parent / "fixtures" / "supervisor_skill_excerpt.md"
    (skill_dir / "SKILL.md").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    MethodologyRAGAgent().run(workspace.root, skills_dir)

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    pre_submission = (
        workspace.root / "rag" / "review_checklists" / "pre_submission_checklist.md"
    ).read_text(encoding="utf-8")
    figure = (workspace.root / "rag" / "review_checklists" / "figure_checklist.md").read_text(
        encoding="utf-8"
    )
    assert hits
    assert "macro logic" in pre_submission
    assert "data source" in figure


def test_methodology_rag_agent_accepts_empty_knowledge_base(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    notes = (workspace.root / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "No user knowledge-base documents were ingested." in notes
    assert (workspace.root / "rag" / "methodology_hits.json").exists()


def test_methodology_rag_agent_ingests_markdown_and_text_knowledge_base(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    (knowledge_base / "methods").mkdir(parents=True)
    (knowledge_base / "methods" / "network_flow.md").write_text(
        "# Network Flow\n\nFigure design should explain min-cost flow decisions.",
        encoding="utf-8",
    )
    (knowledge_base / "rules.txt").write_text(
        "Figure design in MCM papers must connect each chart to a claim.",
        encoding="utf-8",
    )

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    assert {hit["title"] for hit in hits} >= {"network_flow.md", "rules.txt"}
    notes = (workspace.root / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "Ingested user knowledge-base document: methods/network_flow.md" in notes
    assert "Ingested user knowledge-base document: rules.txt" in notes


def test_methodology_rag_agent_reports_pdf_as_pending(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "winning_paper.pdf").write_bytes(b"%PDF")

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    notes = (workspace.root / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "Pending PDF ingestion via MinerU: winning_paper.pdf" in notes


def test_methodology_rag_agent_reports_unsupported_files_as_skipped(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "raw_data.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    notes = (workspace.root / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "Skipped unsupported knowledge-base file: raw_data.csv" in notes


def test_methodology_rag_agent_retrieves_multiple_paper_quality_queries(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "writing_notes.md").write_text(
        "Assumption writing should precede model formulation. "
        "Limitation discussion should connect validation to interpretation. "
        "Figure design should support the main claim.",
        encoding="utf-8",
    )

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    queries = {item["query"] for item in hits}
    assert {
        "assumption writing",
        "model formulation",
        "limitation discussion",
        "figure design",
    } <= queries
