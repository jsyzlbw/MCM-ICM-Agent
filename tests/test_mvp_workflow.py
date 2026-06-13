import json
from pathlib import Path

from mcm_agent.core.models import TaskInput
from mcm_agent.providers.base import ProviderBundle
from mcm_agent.providers.humanizer import FakeHumanizerProvider
from mcm_agent.providers.llm import FakeLLMProvider
from mcm_agent.providers.mineru import ParsedDocument
from mcm_agent.providers.search import SearchResult
from mcm_agent.utils.json_io import read_json
from mcm_agent.workflows.mvp import run_demo_workflow, run_mvp_workflow


class InjectedMinerUProvider:
    def parse_document(self, input_path: Path, output_dir: Path) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "problem.md"
        json_path = output_dir / "problem.json"
        markdown_path.write_text(f"# Injected Parse\n\n{input_path.name}", encoding="utf-8")
        json_path.write_text("{}", encoding="utf-8")
        return ParsedDocument(markdown_path=str(markdown_path), json_path=str(json_path))


class InjectedSearchProvider:
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Injected official source",
                url="https://data.gov/injected",
                snippet="Injected search result.",
                score=1,
            )
        ]


class InjectedExtractProvider:
    def extract(self, url: str):
        return type(
            "ExtractedPage",
            (),
            {
                "url": url,
                "title": "Injected official source",
                "markdown": "# Injected external data",
                "metadata": {},
            },
        )()


def test_run_demo_workflow_creates_required_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"

    run_demo_workflow(workspace, auto_approve=True)

    required = [
        "reports/problem_understanding.md",
        "reports/data_feasibility_report.md",
        "reports/data_feasibility_decision.json",
        "discussion/direction_lock.json",
        "reports/model_candidates.md",
        "reports/model_decision.md",
        "reports/experiment_plan.md",
        "data/source_registry.json",
        "data/data_lineage.json",
        "data/citation_candidates.json",
        "data/retrieval_log.jsonl",
        "review/extraction_gate.json",
        "review/source_gate.json",
        "rag/methodology_hits.json",
        "reports/data_profile.md",
        "results/model_metrics.json",
        "results/evidence_registry.json",
        "results/experiment_runs.jsonl",
        "reports/validation_report.md",
        "review/validation_gate.json",
        "figures/figure_plan.json",
        "figures/figure_registry.json",
        "review/figure_quality_report.md",
        "review/figure_gate.json",
        "paper/main.tex",
        "review/originality_report.md",
        "review/humanization_diff.md",
        "review/fact_regression_report.md",
        "review/reviewer_report.md",
        "review/final_gate.json",
        "review/gate_decisions.json",
        "review/source_audit_report.md",
        "review/methodology_checklist_report.md",
        "final_submission/AI_use_report.md",
    ]
    for relative_path in required:
        assert (workspace / relative_path).exists(), relative_path

    state = read_json(workspace / "task_state.json", {})
    assert [item for item in state["checkpoints"] if item["status"] == "pending"] == []
    stage_runs = [
        json.loads(line)
        for line in (workspace / "stage_runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    stage_ids = [record["stage_id"] for record in stage_runs]
    assert stage_ids[:4] == [
        "intake",
        "mineru_extraction",
        "extraction_quality_gate",
        "problem_understanding",
    ]
    assert "validation_gate" in stage_ids
    assert "figure_quality_gate" in stage_ids
    assert "final_gatekeeper" in stage_ids


def test_run_mvp_workflow_uses_injected_provider_bundle(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nUse the injected provider.", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        humanizer=FakeHumanizerProvider({}),
        latex=object(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        auto_approve=True,
    )

    assert "Injected Parse" in (workspace / "parsed/problem.md").read_text(encoding="utf-8")
    source_registry = read_json(workspace / "data/source_registry.json", [])
    assert source_registry[0]["title"] == "Injected official source"
