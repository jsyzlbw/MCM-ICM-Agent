from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentNode:
    node_id: str
    label: str
    responsibility: str
    input_artifacts: list[str]
    output_artifacts: list[str]
    pass_criteria: list[str]


@dataclass(frozen=True)
class WorkflowEdge:
    from_node: str
    to_node: str
    condition: str = "pass"


@dataclass(frozen=True)
class WorkflowGraph:
    nodes: dict[str, AgentNode]
    edges: list[WorkflowEdge]
    failure_routes: dict[tuple[str, str], str] = field(default_factory=dict)

    def has_edge(self, from_node: str, to_node: str, *, condition: str | None = None) -> bool:
        return any(
            edge.from_node == from_node
            and edge.to_node == to_node
            and (condition is None or edge.condition == condition)
            for edge in self.edges
        )

    def next_nodes(self, node_id: str, *, condition: str = "pass") -> list[str]:
        return [
            edge.to_node
            for edge in self.edges
            if edge.from_node == node_id and edge.condition == condition
        ]

    def failure_route(self, node_id: str, failure_reason: str) -> str:
        try:
            return self.failure_routes[(node_id, failure_reason)]
        except KeyError as exc:
            raise KeyError(f"missing failure route: {node_id}/{failure_reason}") from exc


def build_default_workflow_graph() -> WorkflowGraph:
    nodes = {
        "intake": AgentNode(
            node_id="intake",
            label="Intake Agent",
            responsibility="Collect problem files, templates, attachments, and user idea files.",
            input_artifacts=["raw_user_inputs"],
            output_artifacts=["input_manifest.json"],
            pass_criteria=["All declared input files are copied into the workspace."],
        ),
        "mineru_extraction": AgentNode(
            node_id="mineru_extraction",
            label="MinerU Extraction Agent",
            responsibility="Parse PDF/template/document inputs into structured markdown and JSON.",
            input_artifacts=["input/problem"],
            output_artifacts=["parsed/problem.md", "parsed/problem.json"],
            pass_criteria=["Problem text, equations, tables, and images are captured or flagged."],
        ),
        "extraction_quality_gate": AgentNode(
            node_id="extraction_quality_gate",
            label="Extraction QA Agent",
            responsibility="Check whether the parsed statement is complete enough for reasoning.",
            input_artifacts=["parsed/problem.md", "parsed/problem.json"],
            output_artifacts=["reports/extraction_quality_report.md"],
            pass_criteria=["No critical missing statement, formula, table, or formatting requirement."],
        ),
        "problem_understanding": AgentNode(
            node_id="problem_understanding",
            label="Problem Understanding Agent",
            responsibility="Decompose subtasks, objectives, constraints, metrics, and ambiguities.",
            input_artifacts=["parsed/problem.md"],
            output_artifacts=["reports/problem_understanding.md"],
            pass_criteria=["Every required heading is present and each subproblem has a draft path."],
        ),
        "data_feasibility_scout": AgentNode(
            node_id="data_feasibility_scout",
            label="Data Feasibility Scout",
            responsibility=(
                "Run early search/data checks before user direction is finalized, especially for "
                "private, proprietary, or sparse datasets."
            ),
            input_artifacts=["reports/problem_understanding.md"],
            output_artifacts=["reports/data_feasibility_report.md"],
            pass_criteria=[
                "Critical datasets are classified as available, proxy-needed, or unavailable.",
                "Unavailable data triggers reframing options before user discussion.",
            ],
        ),
        "user_discussion": AgentNode(
            node_id="user_discussion",
            label="User Discussion Agent",
            responsibility=(
                "Discuss feasible routes with the user, send new data-dependent ideas back "
                "to data feasibility checking, and confirm the final research direction."
            ),
            input_artifacts=["reports/problem_understanding.md", "reports/data_feasibility_report.md"],
            output_artifacts=["discussion/confirmed_direction.md"],
            pass_criteria=[
                "The selected direction names data assumptions and fallback choices.",
                "Any newly introduced dataset has passed Data Feasibility Scout.",
            ],
        ),
        "methodology_rag": AgentNode(
            node_id="methodology_rag",
            label="Methodology RAG Agent",
            responsibility="Retrieve modeling methods, paper patterns, and review checklists.",
            input_artifacts=["discussion/confirmed_direction.md"],
            output_artifacts=["rag/methodology_hits.json", "review/methodology_checklist_report.md"],
            pass_criteria=["Relevant methods and checklist items are registered."],
        ),
        "search_data": AgentNode(
            node_id="search_data",
            label="Search & Data Agent",
            responsibility="Retrieve external sources, official APIs, and extract web evidence.",
            input_artifacts=["reports/experiment_plan.md", "reports/data_feasibility_report.md"],
            output_artifacts=["data/source_registry.json", "data/retrieval_log.jsonl"],
            pass_criteria=["Sources are logged, ranked, and persisted."],
        ),
        "source_verifier": AgentNode(
            node_id="source_verifier",
            label="Source Verifier Agent",
            responsibility="Reject unreliable sources and decide whether data can support core claims.",
            input_artifacts=["data/source_registry.json", "data/retrieval_log.jsonl"],
            output_artifacts=["reports/source_verification_report.md"],
            pass_criteria=["Core modeling data is official, academic, user-provided, or justified proxy data."],
        ),
        "data_eda": AgentNode(
            node_id="data_eda",
            label="Data / EDA Agent",
            responsibility="Clean attachments and external data, profile fields, and document limitations.",
            input_artifacts=["input/attachments", "data/source_registry.json"],
            output_artifacts=["reports/data_profile.md", "data/processed"],
            pass_criteria=["Processed data and limitations are available for modeling."],
        ),
        "modeling_council": AgentNode(
            node_id="modeling_council",
            label="Modeling Council",
            responsibility="Generate competing model routes from interpretability, accuracy, and judge views.",
            input_artifacts=["reports/problem_understanding.md", "discussion/confirmed_direction.md"],
            output_artifacts=["reports/model_candidates.md"],
            pass_criteria=["At least two feasible candidates and risks are described."],
        ),
        "model_judge": AgentNode(
            node_id="model_judge",
            label="Model Judge Agent",
            responsibility="Score model candidates and choose an implementable paper route.",
            input_artifacts=["reports/model_candidates.md"],
            output_artifacts=[
                "reports/model_decision.md",
                "reports/experiment_plan.md",
                "reports/experiment_spec.json",
            ],
            pass_criteria=["Selected route is justified by fit, data feasibility, and implementation risk."],
        ),
        "solver_coder": AgentNode(
            node_id="solver_coder",
            label="Solver / Coding Agent",
            responsibility="Write and run code, produce metrics, tables, and evidence.",
            input_artifacts=["reports/experiment_plan.md", "data/processed"],
            output_artifacts=[
                "code",
                "results/model_metrics.json",
                "results/model_route_summary.json",
                "results/solver_binding_report.json",
                "results/evidence_registry.json",
            ],
            pass_criteria=["Code executes and outputs registered evidence."],
        ),
        "validation_gate": AgentNode(
            node_id="validation_gate",
            label="Validation Agent",
            responsibility="Validate results, sensitivity, robustness, and evidence coverage.",
            input_artifacts=["results/model_metrics.json", "results/evidence_registry.json"],
            output_artifacts=["reports/validation_report.md"],
            pass_criteria=["No critical model, data, or evidence gaps remain."],
        ),
        "figure_planning": AgentNode(
            node_id="figure_planning",
            label="Figure Planning Agent",
            responsibility="Plan each figure's claim, source data, target section, and output format.",
            input_artifacts=["reports/model_decision.md", "reports/validation_report.md"],
            output_artifacts=["figures/figure_plan.json"],
            pass_criteria=["Every key claim has a planned figure or explicit no-figure rationale."],
        ),
        "visualization": AgentNode(
            node_id="visualization",
            label="Visualization Agent",
            responsibility="Generate vector-first data plots and concept diagrams.",
            input_artifacts=["figures/figure_plan.json", "data/processed", "results"],
            output_artifacts=["figures/figure_registry.json"],
            pass_criteria=["Data figures have PDF/SVG outputs and reproducible scripts."],
        ),
        "figure_quality_gate": AgentNode(
            node_id="figure_quality_gate",
            label="Figure QA Agent",
            responsibility="Review vector quality, visual consistency, captions, and text placement.",
            input_artifacts=["figures/figure_registry.json"],
            output_artifacts=["review/figure_quality_report.md"],
            pass_criteria=["Figures are readable, cited near use, and fit contest-paper aesthetics."],
        ),
        "paper_writer": AgentNode(
            node_id="paper_writer",
            label="Paper Writer Agent",
            responsibility="Write paper sections using only registered evidence, figures, and sources.",
            input_artifacts=["reports", "figures/figure_registry.json", "results/evidence_registry.json"],
            output_artifacts=["paper/sections"],
            pass_criteria=["No unsupported claims or unresolved placeholders in section drafts."],
        ),
        "typesetting": AgentNode(
            node_id="typesetting",
            label="Typesetting Agent",
            responsibility="Assemble LaTeX, references, figure placement, template rules, and PDF output.",
            input_artifacts=["paper/sections", "figures/figure_registry.json"],
            output_artifacts=["paper/main.tex", "paper/main.pdf"],
            pass_criteria=["Template, page, reference, and figure placement rules are satisfied."],
        ),
        "pre_submission_review": AgentNode(
            node_id="pre_submission_review",
            label="Pre-submission Reviewer",
            responsibility="Run requirement, evidence, format, visual, and originality review panels.",
            input_artifacts=["paper/main.tex", "paper/main.pdf"],
            output_artifacts=["review/reviewer_report.md", "review/originality_report.md"],
            pass_criteria=["Review findings are mapped to responsible repair stages."],
        ),
        "final_gatekeeper": AgentNode(
            node_id="final_gatekeeper",
            label="Final Gatekeeper",
            responsibility="Release only when all blocking review panels pass.",
            input_artifacts=["review"],
            output_artifacts=["final_submission/readiness_decision.json"],
            pass_criteria=["No blocking findings remain."],
        ),
        "submission_packager": AgentNode(
            node_id="submission_packager",
            label="Submission Packager",
            responsibility="Package final paper, source zip, AI use report, manifest, and submission checklist.",
            input_artifacts=["paper/main.pdf", "code", "final_submission/AI_use_report.md"],
            output_artifacts=[
                "final_submission/submission_package.zip",
                "final_submission/source_code.zip",
                "final_submission/submission_manifest.json",
                "final_submission/submission_checklist.md",
            ],
            pass_criteria=["All required submission artifacts exist."],
        ),
        "research_reframing": AgentNode(
            node_id="research_reframing",
            label="Research Reframing Agent",
            responsibility="Convert unavailable private-data plans into proxy-data or alternate-study routes.",
            input_artifacts=["reports/data_feasibility_report.md"],
            output_artifacts=["discussion/reframing_options.md"],
            pass_criteria=["At least one feasible proxy or alternate formulation is ready for user choice."],
        ),
    }
    edges = [
        WorkflowEdge("intake", "mineru_extraction"),
        WorkflowEdge("mineru_extraction", "extraction_quality_gate"),
        WorkflowEdge("extraction_quality_gate", "problem_understanding"),
        WorkflowEdge("problem_understanding", "data_feasibility_scout"),
        WorkflowEdge("data_feasibility_scout", "user_discussion"),
        WorkflowEdge("data_feasibility_scout", "research_reframing", "data_unavailable"),
        WorkflowEdge("research_reframing", "user_discussion"),
        WorkflowEdge("user_discussion", "data_feasibility_scout", "new_data_need"),
        WorkflowEdge("user_discussion", "methodology_rag", "direction_locked"),
        WorkflowEdge("methodology_rag", "modeling_council"),
        WorkflowEdge("modeling_council", "model_judge"),
        WorkflowEdge("model_judge", "search_data"),
        WorkflowEdge("search_data", "source_verifier"),
        WorkflowEdge("source_verifier", "data_eda"),
        WorkflowEdge("data_eda", "solver_coder"),
        WorkflowEdge("solver_coder", "validation_gate"),
        WorkflowEdge("validation_gate", "figure_planning"),
        WorkflowEdge("figure_planning", "visualization"),
        WorkflowEdge("visualization", "figure_quality_gate"),
        WorkflowEdge("figure_quality_gate", "paper_writer"),
        WorkflowEdge("paper_writer", "typesetting"),
        WorkflowEdge("typesetting", "pre_submission_review"),
        WorkflowEdge("pre_submission_review", "final_gatekeeper"),
        WorkflowEdge("final_gatekeeper", "submission_packager"),
    ]
    failure_routes = {
        ("extraction_quality_gate", "missing_problem_text"): "mineru_extraction",
        ("source_verifier", "source_unreliable"): "search_data",
        ("validation_gate", "bad_data"): "search_data",
        ("validation_gate", "weak_model"): "modeling_council",
        ("validation_gate", "code_error"): "solver_coder",
        ("figure_quality_gate", "visual_or_vector_issue"): "figure_planning",
        ("final_gatekeeper", "missing_requirement"): "problem_understanding",
        ("final_gatekeeper", "weak_model"): "modeling_council",
        ("final_gatekeeper", "bad_results"): "solver_coder",
        ("final_gatekeeper", "bad_data"): "search_data",
        ("final_gatekeeper", "bad_figures"): "figure_planning",
        ("final_gatekeeper", "bad_writing"): "paper_writer",
        ("final_gatekeeper", "format_issue"): "typesetting",
    }
    return WorkflowGraph(nodes=nodes, edges=edges, failure_routes=failure_routes)
