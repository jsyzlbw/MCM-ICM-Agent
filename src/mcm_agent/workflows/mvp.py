from __future__ import annotations

from pathlib import Path

from mcm_agent.agents.compliance import ComplianceOriginalityAgent
from mcm_agent.agents.data_feasibility import DataFeasibilityScoutAgent
from mcm_agent.agents.discussion import UserDiscussionAgent
from mcm_agent.agents.eda import DataEDAAgent
from mcm_agent.agents.extraction import DocumentExtractionAgent
from mcm_agent.agents.intake import IntakeAgent
from mcm_agent.agents.modeling import ModelJudge, ModelingCouncil
from mcm_agent.agents.problem_understanding import ProblemUnderstandingAgent
from mcm_agent.agents.rag import MethodologyRAGAgent
from mcm_agent.agents.reference_manager import ReferenceManager
from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.search_data import SearchDataAgent
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.agents.validation import ValidationAgent
from mcm_agent.agents.visualization import FigurePlanningAgent, VisualizationAgent
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import TaskInput
from mcm_agent.core.stage_executor import StageExecutor, StageHandler, StageResult
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderBundle
from mcm_agent.providers.humanizer import FakeHumanizerProvider
from mcm_agent.providers.latex import LatexProvider
from mcm_agent.providers.llm import FakeLLMProvider
from mcm_agent.providers.mineru import FakeMinerUProvider
from mcm_agent.providers.search import SearchResult
from mcm_agent.utils.json_io import read_json
from mcm_agent.workflows.demo_fixtures import create_demo_inputs


class DemoSearchProvider:
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="Demo official dataset",
                url="https://data.gov/demo",
                snippet="A deterministic demo source.",
                score=0.99,
            )
        ]


class DemoExtractProvider:
    def extract(self, url: str):
        return type(
            "ExtractedPage",
            (),
            {
                "url": url,
                "title": "Demo official dataset",
                "markdown": "# Demo official dataset\n\nDeterministic extracted content.",
                "metadata": {},
            },
        )()


def run_mvp_workflow(
    workspace_root: Path,
    inputs: TaskInput,
    *,
    providers: ProviderBundle | None = None,
    supervisor_skills_dir: Path | None = None,
    auto_approve: bool = False,
) -> None:
    workspace = create_workspace(workspace_root)
    provider_bundle = providers or _default_demo_providers()
    executor = StageExecutor(
        workspace.root,
        handlers=_mvp_stage_handlers(
            inputs,
            provider_bundle,
            supervisor_skills_dir=supervisor_skills_dir,
            auto_approve=auto_approve,
        ),
    )
    executor.run_until_complete("intake", terminal_stage="final_gatekeeper")
    if auto_approve:
        _approve_pending_checkpoints(workspace.root)
    _write_ai_use_report(workspace.root)


def resume_mvp_workflow(
    workspace_root: Path,
    inputs: TaskInput,
    *,
    providers: ProviderBundle | None = None,
    supervisor_skills_dir: Path | None = None,
    auto_approve: bool = False,
    from_stage: str | None = None,
    until_stage: str | None = None,
) -> None:
    workspace = create_workspace(workspace_root)
    provider_bundle = providers or _default_demo_providers()
    start_stage = from_stage or _resume_stage_from_state(workspace.root)
    executor = StageExecutor(
        workspace.root,
        handlers=_mvp_stage_handlers(
            inputs,
            provider_bundle,
            supervisor_skills_dir=supervisor_skills_dir,
            auto_approve=auto_approve,
        ),
    )
    executor.run_until_complete(start_stage, terminal_stage=until_stage or "final_gatekeeper")
    if auto_approve:
        _approve_pending_checkpoints(workspace.root)
    _write_ai_use_report(workspace.root)


def run_demo_workflow(workspace_root: Path, *, auto_approve: bool = True) -> None:
    demo_dir = workspace_root.parent / f"{workspace_root.name}_demo_inputs"
    problem, attachments, idea, skills = create_demo_inputs(demo_dir)
    run_mvp_workflow(
        workspace_root,
        TaskInput(problem_file=problem, attachments=attachments, user_idea_file=idea),
        supervisor_skills_dir=skills,
        auto_approve=auto_approve,
    )


def _default_demo_providers() -> ProviderBundle:
    return ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=FakeMinerUProvider(),
        search=DemoSearchProvider(),
        extractor=DemoExtractProvider(),
        humanizer=FakeHumanizerProvider({}),
        latex=LatexProvider(),
    )


def _resume_stage_from_state(workspace_root: Path) -> str:
    state = read_json(workspace_root / "task_state.json", {})
    if isinstance(state, dict):
        repair_stage = state.get("blocked_repair_stage")
        if repair_stage:
            return str(repair_stage)
        current_phase = state.get("current_phase")
        if current_phase and current_phase != "initialized":
            return str(current_phase)
    return "intake"


def _mvp_stage_handlers(
    inputs: TaskInput,
    provider_bundle: ProviderBundle,
    *,
    supervisor_skills_dir: Path | None,
    auto_approve: bool,
) -> dict[str, StageHandler]:
    def intake(workspace_root: Path) -> list[str]:
        IntakeAgent().run(
            workspace_root,
            inputs.problem_file,
            inputs.attachments,
            inputs.user_idea_file,
            inputs.template_dir,
        )
        return ["input_manifest.json"]

    def mineru_extraction(workspace_root: Path) -> list[str]:
        DocumentExtractionAgent(provider_bundle.mineru).run(workspace_root)
        return ["parsed/problem.md", "reports/extraction_quality_report.md"]

    def extraction_quality_gate(workspace_root: Path) -> list[str]:
        return ["review/extraction_gate.json"]

    def problem_understanding(workspace_root: Path) -> list[str]:
        ProblemUnderstandingAgent(provider_bundle.llm).run(workspace_root)
        return ["reports/problem_understanding.md"]

    def data_feasibility_scout(workspace_root: Path) -> StageResult:
        DataFeasibilityScoutAgent(provider_bundle.search).run(workspace_root)
        decision = read_json(workspace_root / "reports" / "data_feasibility_decision.json", {})
        route = decision.get("route", {}) if isinstance(decision, dict) else {}
        condition = "data_unavailable" if route.get("next_stage") == "research_reframing" else "pass"
        return StageResult(
            outputs=["reports/data_feasibility_report.md", "reports/data_feasibility_decision.json"],
            condition=condition,
        )

    def research_reframing(workspace_root: Path) -> list[str]:
        output = workspace_root / "discussion" / "reframing_options.md"
        output.write_text(
            "\n".join(
                [
                    "# Reframing Options",
                    "",
                    "- Use proxy variables when direct private data is unavailable.",
                    "- Ask the user to provide explicit assumptions only if they can justify them.",
                    "- Narrow or change the research question before locking the paper route.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return ["discussion/reframing_options.md"]

    def user_discussion(workspace_root: Path) -> StageResult:
        UserDiscussionAgent().confirm_direction(
            workspace_root,
            mode="ai_led" if auto_approve else "checkpoint_required",
            user_idea_summary="Prefer interpretable and reproducible modeling.",
            selected_route="Balanced contest-paper route.",
            paper_outline="Abstract, assumptions, model, results, sensitivity, conclusion.",
            decisions_to_preserve=["Use vector-first figures.", "Use registered evidence only."],
        )
        lock = read_json(workspace_root / "discussion" / "direction_lock.json", {})
        condition = "new_data_need" if lock.get("status") == "needs_data_scout" else "direction_locked"
        return StageResult(outputs=["discussion/confirmed_direction.md"], condition=condition)

    def methodology_rag(workspace_root: Path) -> list[str]:
        MethodologyRAGAgent().run(workspace_root, supervisor_skills_dir)
        return ["rag/methodology_hits.json", "review/methodology_checklist_report.md"]

    def modeling_council(workspace_root: Path) -> list[str]:
        ModelingCouncil(provider_bundle.llm).run(
            workspace_root,
            workspace_root / "reports" / "problem_understanding.md",
            workspace_root / "discussion" / "confirmed_direction.md",
        )
        return ["reports/model_candidates.md"]

    def model_judge(workspace_root: Path) -> list[str]:
        ModelJudge(provider_bundle.llm).run(
            workspace_root,
            workspace_root / "reports" / "model_candidates.md",
        )
        return ["reports/model_decision.md", "reports/experiment_plan.md"]

    def search_data(workspace_root: Path) -> list[str]:
        SearchDataAgent(provider_bundle.search, provider_bundle.extractor).run(workspace_root)
        return ["data/source_registry.json", "data/retrieval_log.jsonl", "review/source_gate.json"]

    def source_verifier(workspace_root: Path) -> list[str]:
        return ["review/source_gate.json"]

    def data_eda(workspace_root: Path) -> list[str]:
        DataEDAAgent().run(workspace_root)
        return ["reports/data_profile.md", "data/processed"]

    def solver_coder(workspace_root: Path) -> list[str]:
        SolverCoderAgent().run(workspace_root)
        return [
            "code",
            "results/model_metrics.json",
            "results/model_route_summary.json",
            "results/evidence_registry.json",
        ]

    def validation_gate(workspace_root: Path) -> list[str]:
        ValidationAgent().run(workspace_root)
        return ["reports/validation_report.md", "review/validation_gate.json"]

    def figure_planning(workspace_root: Path) -> list[str]:
        FigurePlanningAgent().run(workspace_root)
        return ["figures/figure_plan.json"]

    def visualization(workspace_root: Path) -> list[str]:
        VisualizationAgent().run(workspace_root)
        return ["figures/figure_registry.json", "review/figure_gate.json"]

    def figure_quality_gate(workspace_root: Path) -> list[str]:
        from mcm_agent.agents.figure_quality import FigureQualityAgent

        FigureQualityAgent().run(workspace_root)
        return ["review/figure_quality_report.md", "review/figure_gate.json"]

    def paper_writer(workspace_root: Path) -> list[str]:
        PaperWriterAgent(provider_bundle.llm).run(workspace_root)
        return ["paper/main.tex", "paper/sections"]

    def typesetting(workspace_root: Path) -> list[str]:
        ComplianceOriginalityAgent(provider_bundle.humanizer).run(workspace_root)
        ReferenceManager().run(workspace_root)
        return [
            "paper/main.tex",
            "paper/references.bib",
            "review/originality_report.md",
            "review/reference_audit_report.md",
        ]

    def pre_submission_review(workspace_root: Path) -> list[str]:
        ReviewerAgent(provider_bundle.llm).run(workspace_root)
        return ["review/reviewer_report.md", "review/final_gate.json"]

    def final_gatekeeper(workspace_root: Path) -> list[str]:
        return ["review/final_gate.json"]

    handlers: dict[str, StageHandler] = {
        "intake": intake,
        "mineru_extraction": mineru_extraction,
        "extraction_quality_gate": extraction_quality_gate,
        "problem_understanding": problem_understanding,
        "data_feasibility_scout": data_feasibility_scout,
        "research_reframing": research_reframing,
        "user_discussion": user_discussion,
        "methodology_rag": methodology_rag,
        "modeling_council": modeling_council,
        "model_judge": model_judge,
        "search_data": search_data,
        "source_verifier": source_verifier,
        "data_eda": data_eda,
        "solver_coder": solver_coder,
        "validation_gate": validation_gate,
        "figure_planning": figure_planning,
        "visualization": visualization,
        "figure_quality_gate": figure_quality_gate,
        "paper_writer": paper_writer,
        "typesetting": typesetting,
        "pre_submission_review": pre_submission_review,
        "final_gatekeeper": final_gatekeeper,
    }
    return handlers


def _write_ai_use_report(workspace_root: Path) -> None:
    final_dir = workspace_root / "final_submission"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "AI_use_report.md").write_text(
        "\n".join(
            [
                "# AI Use Report",
                "",
                "## Tools Used",
                "- MCM Agent reference implementation.",
                "",
                "## Human Decisions",
                "- Demo mode auto-approved checkpoints.",
                "",
                "## AI-Assisted Steps",
                "- Planning, writing, validation, and review scaffolds.",
                "",
                "## Verification Steps",
                "- Evidence registry, figure registry, and fact regression checks.",
                "",
                "## External Services",
                "- Demo run used fake providers only.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _approve_pending_checkpoints(workspace_root: Path) -> None:
    coordinator = Coordinator(workspace_root)
    state = read_json(workspace_root / "task_state.json", {})
    for checkpoint in state.get("checkpoints", []):
        if checkpoint.get("status") == "pending":
            coordinator.approve_checkpoint(
                checkpoint["checkpoint_id"],
                user_message="Auto-approved by deterministic demo workflow.",
            )
