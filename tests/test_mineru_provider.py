from pathlib import Path

from mcm_agent.agents.extraction import DocumentExtractionAgent
from mcm_agent.agents.intake import IntakeAgent
from mcm_agent.core.events import EventLog
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.mineru import FakeMinerUProvider
from mcm_agent.utils.json_io import read_json


def test_fake_mineru_parses_markdown_problem(tmp_path: Path) -> None:
    problem = tmp_path / "problem.md"
    problem.write_text("# Problem\n\nBuild a model.", encoding="utf-8")

    parsed = FakeMinerUProvider().parse_document(problem, tmp_path / "parsed")

    assert Path(parsed.markdown_path).read_text(encoding="utf-8") == "# Problem\n\nBuild a model."
    assert Path(parsed.json_path).exists()
    assert Path(parsed.layout_path or "").exists()
    assert Path(parsed.formula_path or "").exists()


def test_fake_mineru_parses_pdf_placeholder(tmp_path: Path) -> None:
    problem = tmp_path / "problem.pdf"
    problem.write_bytes(b"%PDF fake")

    parsed = FakeMinerUProvider().parse_document(problem, tmp_path / "parsed")

    assert "Fake MinerU output for problem.pdf" in Path(parsed.markdown_path).read_text(
        encoding="utf-8"
    )


def test_intake_agent_copies_inputs_and_emits_event(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    idea = tmp_path / "idea.md"
    problem.write_text("# Problem", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n", encoding="utf-8")
    idea.write_text("Use a simple baseline.", encoding="utf-8")

    IntakeAgent().run(workspace.root, problem, [attachment], idea, None)

    manifest = read_json(workspace.root / "input_manifest.json", {})
    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert manifest["problem_file"] == "input/problem.md"
    assert (workspace.root / "input/attachments/data.csv").exists()
    assert events[-1].event_type == "input.received"


def test_extraction_agent_writes_outputs_registry_and_event(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem = tmp_path / "problem.md"
    problem.write_text("# Problem\n\nBuild a model.", encoding="utf-8")
    IntakeAgent().run(workspace.root, problem, [], None, None)

    DocumentExtractionAgent(FakeMinerUProvider()).run(workspace.root)

    registry = ArtifactRegistry(workspace.root / "artifact_registry.json")
    events = EventLog(workspace.root / "event_log.jsonl").read_all()
    assert (workspace.root / "parsed/problem.md").exists()
    assert (workspace.root / "reports/extraction_quality_report.md").exists()
    assert registry.get("parsed_problem_v1").path == "parsed/problem.md"
    assert events[-1].event_type == "document.parsed"
