import json
from pathlib import Path

from mcm_agent.config import Settings
from mcm_agent.core.models import TaskInput
from mcm_agent.providers.base import ProviderBundle
from mcm_agent.providers.humanizer import FakeHumanizerProvider
from mcm_agent.providers.latex import LatexCompileResult
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
        source = input_path.read_text(encoding="utf-8")
        markdown_path.write_text(f"# Injected Parse\n\n{source}", encoding="utf-8")
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


class InjectedLatexProvider:
    def compile(self, paper_dir: Path) -> LatexCompileResult:
        pdf = paper_dir / "main.pdf"
        pdf.write_bytes(b"%PDF injected")
        return LatexCompileResult(
            success=True,
            pdf_path=str(pdf),
            log_path=str(paper_dir / "compile_log.txt"),
        )


def test_run_demo_workflow_creates_required_artifacts(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"

    run_demo_workflow(workspace, auto_approve=True)

    required = [
        "reports/problem_understanding.md",
        "reports/data_feasibility_report.md",
        "reports/data_feasibility_decision.json",
        "data/data_feasibility_matrix.json",
        "discussion/direction_lock.json",
        "reports/model_candidates.md",
        "reports/model_decision.md",
        "reports/experiment_plan.md",
        "reports/experiment_spec.json",
        "reports/modeling_quality_report.md",
        "review/modeling_gate.json",
        "data/source_registry.json",
        "data/data_lineage.json",
        "data/citation_candidates.json",
        "data/retrieval_log.jsonl",
        "review/extraction_gate.json",
        "review/source_gate.json",
        "rag/methodology_hits.json",
        "reports/data_profile.md",
        "results/model_metrics.json",
        "results/model_route_summary.json",
        "results/solver_binding_report.json",
        "results/evidence_registry.json",
        "results/experiment_runs.jsonl",
        "reports/validation_report.md",
        "review/validation_gate.json",
        "figures/figure_plan.json",
        "figures/figure_registry.json",
        "review/figure_quality_report.md",
        "review/figure_gate.json",
        "paper/claim_plan.json",
        "review/claim_plan_report.md",
        "paper/main.tex",
        "review/paper_evidence_bindings.json",
        "review/paper_evidence_report.md",
        "review/originality_report.md",
        "review/humanization_diff.md",
        "review/fact_regression_report.md",
        "review/typesetting_quality.json",
        "review/typesetting_quality_report.md",
        "review/reviewer_report.md",
        "review/paper_quality_scores.json",
        "review/final_gate.json",
        "review/gate_decisions.json",
        "review/source_audit_report.md",
        "review/methodology_checklist_report.md",
        "final_submission/AI_use_report.md",
        "final_submission/submission_manifest.json",
        "final_submission/submission_package.zip",
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
    assert stage_ids.index("figure_quality_gate") < stage_ids.index("claim_planning")
    assert stage_ids.index("claim_planning") < stage_ids.index("paper_writer")
    assert "final_gatekeeper" in stage_ids
    assert stage_ids[-1] == "submission_packager"
    paper_quality = read_json(workspace / "review" / "paper_quality_scores.json", {})
    assert paper_quality["status"] == "pass"
    abstract = (workspace / "paper" / "sections" / "abstract.tex").read_text(
        encoding="utf-8"
    )
    introduction = (workspace / "paper" / "sections" / "introduction.tex").read_text(
        encoding="utf-8"
    )
    assumptions = (workspace / "paper" / "sections" / "assumptions.tex").read_text(
        encoding="utf-8"
    )
    assert "traceable" in abstract.lower() or "model" in abstract.lower()
    assert "planned claim chain" in introduction
    assert "assumption" in assumptions.lower()


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
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=InjectedLatexProvider(),
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
    assert (workspace / "final_submission" / "submission_package.zip").exists()


def test_run_mvp_workflow_uses_configured_rag_knowledge_base(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nUse a local knowledge base.", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "method_note.md").write_text(
        "Figure design should map every result plot to the claim it supports.",
        encoding="utf-8",
    )
    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=InjectedLatexProvider(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        settings=Settings(rag_knowledge_base_dir=str(knowledge_base)),
        auto_approve=True,
    )

    hits = read_json(workspace / "rag" / "methodology_hits.json", [])
    assert any(hit["title"] == "method_note.md" for hit in hits)


def test_run_mvp_workflow_uses_configured_mineru_for_rag_pdf(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "data.csv"
    problem.write_text("# Problem\n\nUse a local PDF knowledge base.", encoding="utf-8")
    attachment.write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "paper_example.pdf").write_bytes(b"%PDF")
    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=InjectedLatexProvider(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        settings=Settings(rag_knowledge_base_dir=str(knowledge_base)),
        auto_approve=True,
    )

    notes = (workspace / "rag" / "retrieval_notes.md").read_text(encoding="utf-8")
    assert "Parsed PDF knowledge-base document via MinerU: paper_example.pdf" in notes


def test_run_mvp_workflow_selects_forecast_simulation_network_routes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "network_demand.csv"
    problem.write_text(
        "# Problem\n\nForecast evacuation demand, simulate uncertainty, and route traffic through a network.",
        encoding="utf-8",
    )
    attachment.write_text(
        "source,target,cost,period,demand\nA,B,1,1,10\nB,C,2,2,12\nA,C,5,3,14\n",
        encoding="utf-8",
    )
    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=InjectedLatexProvider(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        auto_approve=True,
    )

    summary = read_json(workspace / "results" / "model_route_summary.json", {})
    assert "forecasting_model" in summary["selected_routes"]
    assert "monte_carlo_simulation" in summary["selected_routes"]
    assert "network_flow_graph" in summary["selected_routes"]
    assert summary["route_execution_status"]["forecasting_model"] == "executed"


def test_run_mvp_workflow_selects_classification_clustering_queuing_routes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "service.csv"
    problem.write_text(
        "# Problem\n\nClassify risk levels, cluster service regions, and estimate queue waiting time.",
        encoding="utf-8",
    )
    attachment.write_text(
        "feature_a,feature_b,risk_label,segment_value,arrival_rate,service_rate,servers\n"
        "0,0,0,1,2.0,3.0,2\n"
        "1,1,0,1.2,2.2,3.1,2\n"
        "4,3,1,8,2.4,3.2,2\n"
        "5,4,1,8.2,2.1,3.0,2\n",
        encoding="utf-8",
    )
    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=InjectedLatexProvider(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        auto_approve=True,
    )

    summary = read_json(workspace / "results" / "model_route_summary.json", {})
    assert "classification_model" in summary["selected_routes"]
    assert "clustering_segmentation" in summary["selected_routes"]
    assert "queuing_service_model" in summary["selected_routes"]
