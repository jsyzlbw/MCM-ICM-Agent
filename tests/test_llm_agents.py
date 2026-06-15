from pathlib import Path

from mcm_agent.agents.modeling import ModelJudge, ModelingCouncil
from mcm_agent.agents.reviewer import ReviewerAgent
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult
from mcm_agent.utils.json_io import write_json


class StaticLLMProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        self.calls.append((system, prompt))
        return ProviderResult(content=self.content, metadata={"fake": True})


def test_modeling_council_uses_valid_llm_output(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem_report = workspace.root / "reports" / "problem_understanding.md"
    direction = workspace.root / "discussion" / "direction_lock.json"
    problem_report.write_text("# Problem Understanding\n\nNeed a salary policy model.", encoding="utf-8")
    direction.write_text('{"status":"approved"}', encoding="utf-8")
    provider = StaticLLMProvider(
        "\n".join(
            [
                "# Model Candidates",
                "",
                "## Candidate Summary Table",
                "| Role | Candidate | Main Strength |",
                "|---|---|---|",
                "| judge | LLM salary proxy route | traceable assumptions |",
                "",
                "## Data Limitations",
                "- source_id: web_001 may only provide proxy salary data.",
                "",
                "## Cross-Candidate Risks",
                "- Do not assume private compensation data is public.",
                "",
            ]
        )
    )

    ModelingCouncil(provider).run(workspace.root, problem_report, direction)

    text = (workspace.root / "reports" / "model_candidates.md").read_text(encoding="utf-8")
    assert "LLM salary proxy route" in text
    assert provider.calls


def test_model_judge_falls_back_on_invalid_llm_output(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    candidates = workspace.root / "reports" / "model_candidates.md"
    candidates.write_text("# Model Candidates\n\nbad but present", encoding="utf-8")

    ModelJudge(StaticLLMProvider("too short")).run(workspace.root, candidates)

    decision = (workspace.root / "reports" / "model_decision.md").read_text(encoding="utf-8")
    assert "Balanced contest-paper route" in decision
    assert "## Data Limitations" in decision


def test_paper_writer_uses_valid_llm_results_section_with_trace_ids(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "ev_metric_001"}],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_q1_prediction"}],
    )
    write_json(
        workspace.root / "data" / "source_registry.json",
        [{"source_id": "web_001"}],
    )
    provider = StaticLLMProvider(
        "\\section{Results}\nThe main result references evidence_id=ev_metric_001, "
        "figure_id=fig_q1_prediction, and source_id=web_001.\n"
    )

    PaperWriterAgent(provider).run(workspace.root)

    results = (workspace.root / "paper" / "sections" / "results.tex").read_text(encoding="utf-8")
    assert "evidence_id=ev_metric_001" in results
    assert "figure_id=fig_q1_prediction" in results
    assert "source_id=web_001" in results


def test_paper_writer_includes_selected_model_route_summary(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "results" / "model_route_summary.json",
        {
            "selected_routes": ["multi_criteria_evaluation", "constrained_optimization"],
            "route_metrics": {
                "priority_score_mean": {
                    "route_id": "multi_criteria_evaluation",
                    "value": 0.6,
                },
                "allocation_capacity_total": {
                    "route_id": "constrained_optimization",
                    "value": 16.0,
                },
            },
        },
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [])
    write_json(workspace.root / "figures" / "figure_registry.json", [])
    write_json(workspace.root / "data" / "source_registry.json", [])

    PaperWriterAgent().run(workspace.root)

    model_section = (workspace.root / "paper" / "sections" / "model.tex").read_text(
        encoding="utf-8"
    )
    assert "multi\\_criteria\\_evaluation + constrained\\_optimization" in model_section
    assert "priority\\_score\\_mean=0.6" in model_section
    assert "allocation\\_capacity\\_total=16.0" in model_section


def test_paper_writer_builds_evidence_driven_results_and_sensitivity(
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
                "top_priority_entity": {
                    "route_id": "multi_criteria_evaluation",
                    "value": "A",
                },
            },
        },
    )
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [
            {
                "evidence_id": "metric_priority_score_mean",
                "claim": "Route metric priority_score_mean equals 0.6.",
                "value": 0.6,
                "source_type": "code_output",
                "source_path": "results/model_route_summary.json",
                "generated_by": "code/experiments/problem1.py",
                "used_in": ["multi_criteria_evaluation"],
                "verified": True,
            }
        ],
    )
    write_json(
        workspace.root / "figures" / "figure_registry.json",
        [{"figure_id": "fig_priority_ranking", "caption_intent": "Priority ranking."}],
    )
    write_json(workspace.root / "data" / "source_registry.json", [{"source_id": "web_001"}])

    PaperWriterAgent().run(workspace.root)

    results = (workspace.root / "paper" / "sections" / "results.tex").read_text(
        encoding="utf-8"
    )
    sensitivity = (workspace.root / "paper" / "sections" / "sensitivity.tex").read_text(
        encoding="utf-8"
    )
    assert "metric\\_priority\\_score\\_mean" in results
    assert "fig\\_priority\\_ranking" in results
    assert "source\\_id=web\\_001" in results
    assert "priority\\_score\\_mean=0.6" in sensitivity
    assert "top\\_priority\\_entity=A" in sensitivity


def test_reviewer_falls_back_on_invalid_llm_output(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")

    ReviewerAgent(StaticLLMProvider("invalid")).run(workspace.root)

    report = (workspace.root / "review" / "reviewer_report.md").read_text(encoding="utf-8")
    assert "# 自动评审报告" in report
    assert "## 高风险问题" in report


def test_paper_writer_renders_contextual_abstract_intro_and_assumptions(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "# Problem Understanding\n\nNeed an evacuation allocation model.",
        encoding="utf-8",
    )
    (workspace.root / "discussion" / "confirmed_direction.md").write_text(
        "# Confirmed Direction\n\nUse interpretable optimization.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "paper" / "claim_plan.json",
        [
            {
                "claim_id": "claim_assumption_problem_context",
                "section": "paper/sections/assumptions.tex",
                "claim_text": "Capacity assumptions define feasible allocation.",
                "claim_type": "assumption",
                "evidence_ids": ["ev_capacity"],
                "priority": "major",
            },
            {
                "claim_id": "claim_model_route",
                "section": "paper/sections/model.tex",
                "claim_text": "The selected model combines ranking and allocation.",
                "claim_type": "model_choice",
                "evidence_ids": ["ev_capacity"],
                "priority": "critical",
            },
        ],
    )
    write_json(workspace.root / "results" / "evidence_registry.json", [{"evidence_id": "ev_capacity"}])

    PaperWriterAgent().run(workspace.root)

    abstract = (workspace.root / "paper" / "sections" / "abstract.tex").read_text(
        encoding="utf-8"
    )
    introduction = (workspace.root / "paper" / "sections" / "introduction.tex").read_text(
        encoding="utf-8"
    )
    assumptions = (workspace.root / "paper" / "sections" / "assumptions.tex").read_text(
        encoding="utf-8"
    )
    assert "evacuation allocation" in abstract
    assert "interpretable optimization" in introduction
    assert "Capacity assumptions define feasible allocation" in assumptions
    assert "% claim_id=claim_assumption_problem_context evidence_id=ev_capacity" in assumptions
