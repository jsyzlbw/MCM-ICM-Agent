from pathlib import Path

from mcm_agent.agents.rag import MethodologyRAGAgent, MethodologyStore
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


class KnowledgeBaseMinerUProvider:
    def parse_document(self, input_path: Path, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        markdown_path.write_text(
            "# Parsed Paper\n\nFigure design should explain the validation claim.",
            encoding="utf-8",
        )
        json_path.write_text("{}", encoding="utf-8")
        return type(
            "Parsed",
            (),
            {
                "markdown_path": str(markdown_path),
                "json_path": str(json_path),
                "page_count": 3,
                "warnings": ["low confidence table"],
            },
        )()


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


def test_methodology_hits_include_provenance_and_usage_restrictions(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    (knowledge_base / "contest_rules").mkdir(parents=True)
    (knowledge_base / "contest_rules" / "rules.txt").write_text(
        "Figure design must keep every chart tied to an explicit paper claim.",
        encoding="utf-8",
    )

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    rule_hit = next(hit for hit in hits if hit["title"] == "rules.txt")
    assert rule_hit["source_type"] == "contest_rule"
    assert rule_hit["relative_path"] == "contest_rules/rules.txt"
    assert rule_hit["chunk_id"] == "contest_rules/rules.txt#chunk-001"
    assert rule_hit["usage"] == (
        "Use as contest or formatting guidance only; do not cite as external factual data."
    )


def test_methodology_rag_agent_chunks_large_knowledge_base_documents(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    first = "Figure design should explain the model claim. " * 80
    second = "Model formulation should define variables and constraints. " * 80
    (knowledge_base / "method_note.md").write_text(first + "\n\n" + second, encoding="utf-8")

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    chunk_ids = {hit["chunk_id"] for hit in hits if hit["title"] == "method_note.md"}
    assert "method_note.md#chunk-001" in chunk_ids
    assert "method_note.md#chunk-002" in chunk_ids


def test_methodology_rag_agent_ingests_pdf_knowledge_base_with_mineru(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    knowledge_base = tmp_path / "knowledge_base"
    (knowledge_base / "winning_papers").mkdir(parents=True)
    (knowledge_base / "winning_papers" / "solution.pdf").write_bytes(b"%PDF")

    MethodologyRAGAgent().run(
        workspace.root,
        supervisor_skills_dir=None,
        knowledge_base_dir=knowledge_base,
        mineru_provider=KnowledgeBaseMinerUProvider(),
    )

    hits = read_json(workspace.root / "rag" / "methodology_hits.json", [])
    parsed_hit = next(hit for hit in hits if hit["title"] == "solution.pdf")
    assert parsed_hit["source_type"] == "paper_example"
    assert parsed_hit["relative_path"] == "winning_papers/solution.pdf"
    assert parsed_hit["page_hint"] == "pages=3"
    assert "validation claim" in parsed_hit["content"]
    notes = (workspace.root / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "Parsed PDF knowledge-base document via MinerU: winning_papers/solution.pdf" in notes
    assert "MinerU warning for winning_papers/solution.pdf: low confidence table" in notes
