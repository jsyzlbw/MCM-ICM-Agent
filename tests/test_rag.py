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
