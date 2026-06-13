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
from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.search_data import SearchDataAgent
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.agents.validation import ValidationAgent
from mcm_agent.agents.visualization import FigurePlanningAgent, VisualizationAgent
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import TaskInput
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
    IntakeAgent().run(
        workspace.root,
        inputs.problem_file,
        inputs.attachments,
        inputs.user_idea_file,
        inputs.template_dir,
    )
    DocumentExtractionAgent(provider_bundle.mineru).run(workspace.root)
    ProblemUnderstandingAgent(provider_bundle.llm).run(workspace.root)
    DataFeasibilityScoutAgent(provider_bundle.search).run(workspace.root)
    UserDiscussionAgent().confirm_direction(
        workspace.root,
        mode="ai_led" if auto_approve else "checkpoint_required",
        user_idea_summary="Prefer interpretable and reproducible modeling.",
        selected_route="Balanced contest-paper route.",
        paper_outline="Abstract, assumptions, model, results, sensitivity, conclusion.",
        decisions_to_preserve=["Use vector-first figures.", "Use registered evidence only."],
    )
    ModelingCouncil().run(
        workspace.root,
        workspace.root / "reports" / "problem_understanding.md",
        workspace.root / "discussion" / "confirmed_direction.md",
    )
    ModelJudge().run(workspace.root, workspace.root / "reports" / "model_candidates.md")
    SearchDataAgent(provider_bundle.search, provider_bundle.extractor).run(workspace.root)
    MethodologyRAGAgent().run(workspace.root, supervisor_skills_dir)
    DataEDAAgent().run(workspace.root)
    SolverCoderAgent().run(workspace.root)
    ValidationAgent().run(workspace.root)
    FigurePlanningAgent().run(workspace.root)
    VisualizationAgent().run(workspace.root)
    PaperWriterAgent().run(workspace.root)
    ComplianceOriginalityAgent(provider_bundle.humanizer).run(workspace.root)
    ReviewerAgent().run(workspace.root)
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
