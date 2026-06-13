from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.modeling_intelligence import ModelingIntelligence, ProblemDiagnosis
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.providers.base import TextGenerationProvider


COUNCIL_ROLES = [
    "simple_interpretable_modeler",
    "high_accuracy_modeler",
    "optimization_modeler",
    "judge_perspective_modeler",
]

WEIGHTS = {
    "problem_fit": 0.30,
    "data_feasibility": 0.25,
    "explainability": 0.20,
    "implementation_risk": 0.15,
    "paper_quality_potential": 0.10,
}


class ModelingCouncil:
    def __init__(self, llm_provider: TextGenerationProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run(
        self,
        workspace_root: Path,
        problem_report_path: Path,
        confirmed_direction_path: Path,
    ) -> None:
        problem_excerpt = problem_report_path.read_text(encoding="utf-8")[:600]
        direction_excerpt = confirmed_direction_path.read_text(encoding="utf-8")[:600]
        llm_output = self._generate_candidates(problem_excerpt, direction_excerpt)
        if llm_output is not None:
            lines = llm_output.splitlines()
        else:
            lines = self._fallback_candidates(problem_excerpt, direction_excerpt)

        path = workspace_root / "reports" / "model_candidates.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        registry = ArtifactRegistry(workspace_root / "artifact_registry.json")
        self._upsert_artifact(
            registry,
            ArtifactRecord(
                artifact_id="model_candidates_v1",
                type="model_candidates",
                path="reports/model_candidates.md",
                producer="ModelingCouncil",
                depends_on=["problem_understanding_v1", "confirmed_direction_v1"],
                status=ArtifactStatus.APPROVED,
                created_at=datetime.now(UTC),
            ),
        )
        Coordinator(workspace_root).emit(
            "model.candidates.ready",
            payload={"artifact_ids": ["model_candidates_v1"]},
            source="ModelingCouncil",
        )

    def _fallback_candidates(self, problem_excerpt: str, direction_excerpt: str) -> list[str]:
        diagnosis = ModelingIntelligence().diagnose(f"{problem_excerpt}\n{direction_excerpt}")
        lines = [
            "# Model Candidates",
            "",
            "## Problem Type Diagnosis",
            "",
            "- Primary problem types: " + ", ".join(diagnosis.primary_problem_types),
            "",
            "## Recommended Model Routes",
            "",
            "| Route ID | Candidate | Problem Type | Main Strength | Risk |",
            "|---|---|---|---|---|",
        ]
        for route in diagnosis.routes:
            lines.append(
                f"| {route.route_id} | {route.candidate} | {route.problem_type} | "
                f"{route.main_strength} | {route.implementation_risk} |"
            )
        lines.extend(
            [
                "",
                "## Route Details",
                "",
            ]
        )
        for route in diagnosis.routes:
            lines.extend(
                [
                    f"### {route.route_id}",
                    "",
                    f"Candidate: {route.candidate}",
                    "",
                    f"Methods: {', '.join(route.methods)}",
                    "",
                    f"Metrics: {', '.join(route.metrics)}",
                    "",
                    f"Data needs: {', '.join(route.data_needs)}.",
                    "",
                ]
            )
        lines.extend(
            [
            "## Candidate Summary Table",
            "",
            "| Role | Candidate | Main Strength |",
            "|---|---|---|",
            ]
        )
        for role in COUNCIL_ROLES:
            lines.append(f"| {role} | {self._candidate_name(role)} | {self._strength(role)} |")

        lines.extend(["", "<!-- Context Snapshot -->", problem_excerpt, direction_excerpt, ""])
        for role in COUNCIL_ROLES:
            lines.extend(
                [
                    f"## {role}",
                    "",
                    f"Candidate: {self._candidate_name(role)}",
                    "",
                    f"Rationale: {self._strength(role)}",
                    "",
                    "Data needs: cleaned attachments and any registered external data.",
                    "",
                    "Implementation risk: medium.",
                    "",
                ]
            )
        lines.extend(
            [
                "## Data Limitations",
                "",
                *(f"- {limitation}" for limitation in diagnosis.data_limitations),
                "- source_id: registered external data may be incomplete or unavailable.",
                "",
                "## Cross-Candidate Risks",
                "",
                "- Avoid choosing a model that cannot be supported by available data.",
                "- Prefer explainable baselines unless additional complexity clearly improves the paper.",
                "",
            ]
        )
        return lines

    def _generate_candidates(self, problem_excerpt: str, direction_excerpt: str) -> str | None:
        if self.llm_provider is None:
            return None
        prompt = "\n".join(
            [
                "# Modeling Council",
                "",
                "Generate model candidates for an MCM/ICM paper.",
                "Required headings: # Model Candidates, ## Candidate Summary Table, "
                "## Data Limitations, ## Cross-Candidate Risks.",
                "The plan must cite source_id-style data references or explicitly state "
                "which source_id is missing.",
                "",
                "Problem excerpt:",
                problem_excerpt,
                "",
                "Confirmed direction:",
                direction_excerpt,
            ]
        )
        result = self.llm_provider.generate("You are a math modeling research planner.", prompt)
        content = result.content.strip()
        required = [
            "# Model Candidates",
            "## Candidate Summary Table",
            "## Data Limitations",
            "## Cross-Candidate Risks",
        ]
        if all(heading in content for heading in required) and "source_id" in content:
            return content
        return None

    def _candidate_name(self, role: str) -> str:
        return {
            "simple_interpretable_modeler": "Interpretable baseline with sensitivity analysis",
            "high_accuracy_modeler": "Feature-rich predictive ensemble",
            "optimization_modeler": "Constrained optimization policy model",
            "judge_perspective_modeler": "Balanced contest-paper route",
        }[role]

    def _strength(self, role: str) -> str:
        return {
            "simple_interpretable_modeler": "Clear assumptions and easy validation",
            "high_accuracy_modeler": "Potentially stronger predictive metrics",
            "optimization_modeler": "Directly supports decision recommendations",
            "judge_perspective_modeler": "Best balance of readability and rigor",
        }[role]

    def _upsert_artifact(self, registry: ArtifactRegistry, record: ArtifactRecord) -> None:
        try:
            registry.add(record)
        except ValueError:
            registry.update_status(record.artifact_id, record.status)


class ModelJudge:
    def __init__(self, llm_provider: TextGenerationProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run(self, workspace_root: Path, candidates_path: Path) -> None:
        if not candidates_path.exists():
            raise FileNotFoundError(candidates_path)

        candidates_text = candidates_path.read_text(encoding="utf-8")
        candidates_excerpt = candidates_text[:1200]
        diagnosis = self._diagnosis_from_candidates(candidates_text)
        decision = self._generate_decision(candidates_excerpt) or self._fallback_decision(
            diagnosis if diagnosis.routes else None
        )
        experiment_plan = self._fallback_experiment_plan(diagnosis)

        (workspace_root / "reports" / "model_decision.md").write_text(decision, encoding="utf-8")
        (workspace_root / "reports" / "experiment_plan.md").write_text(
            experiment_plan,
            encoding="utf-8",
        )

        registry = ArtifactRegistry(workspace_root / "artifact_registry.json")
        now = datetime.now(UTC)
        for record in [
            ArtifactRecord(
                artifact_id="model_decision_v1",
                type="model_decision",
                path="reports/model_decision.md",
                producer="ModelJudge",
                depends_on=["model_candidates_v1"],
                status=ArtifactStatus.REVIEW_REQUIRED,
                created_at=now,
            ),
            ArtifactRecord(
                artifact_id="experiment_plan_v1",
                type="experiment_plan",
                path="reports/experiment_plan.md",
                producer="ModelJudge",
                depends_on=["model_decision_v1"],
                status=ArtifactStatus.REVIEW_REQUIRED,
                created_at=now,
            ),
        ]:
            try:
                registry.add(record)
            except ValueError:
                registry.update_status(record.artifact_id, record.status)

        coordinator = Coordinator(workspace_root)
        coordinator.emit("model.candidates.ready", payload={"artifact_ids": ["model_candidates_v1"]}, source="ModelJudge")
        coordinator.emit(
            "model.decision.ready",
            payload={"artifact_ids": ["model_decision_v1", "experiment_plan_v1"]},
            source="ModelJudge",
        )

    def _fallback_decision(self, diagnosis: ProblemDiagnosis | None = None) -> str:
        route_ids = [route.route_id for route in diagnosis.routes[:2]] if diagnosis else []
        selected_route = " + ".join(route_ids) if route_ids else "Balanced contest-paper route"
        scores = {
            selected_route: {
                "problem_fit": 9,
                "data_feasibility": 8,
                "explainability": 9,
                "implementation_risk": 8,
                "paper_quality_potential": 9,
            }
        }
        total = sum(scores[selected_route][key] * weight for key, weight in WEIGHTS.items())

        return "\n".join(
            [
                "# Model Decision",
                "",
                "## Selected Route",
                f"{selected_route}. Weighted score: {total:.2f}.",
                "",
                "## Rejected Alternatives",
                "- Pure high-accuracy route: higher implementation and explanation risk.",
                "- Pure optimization route: may under-serve predictive subtasks.",
                "",
                "## Mathematical Formulation",
                self._formulation_summary(diagnosis) if diagnosis else "Use a readable baseline model with sensitivity analysis.",
                "",
                "## Objective Functions",
                self._objective_summary(diagnosis) if diagnosis else "Minimize prediction error and optimize the final decision metric.",
                "",
                "## Constraints",
                "Respect data availability, contest format, and model interpretability constraints.",
                "",
                "## Data Requirements",
                "Use cleaned attachments and registered external data only.",
                "",
                "## Data Limitations",
                "If direct data is private or unavailable, use registered proxy variables and state assumptions.",
                "",
                "## Figure Requirements",
                "Include a model framework diagram, result comparison chart, and sensitivity plot.",
                "",
                "## Sensitivity Analysis Plan",
                "Perturb key parameters and report ranking or prediction stability.",
                "",
            ]
        )

    def _fallback_experiment_plan(self, diagnosis: ProblemDiagnosis | None = None) -> str:
        metrics = sorted({metric for route in diagnosis.routes for metric in route.metrics}) if diagnosis else []
        return "\n".join(
            [
                "# Experiment Plan",
                "",
                "## Required Datasets",
                "- Cleaned attachment tables.",
                "",
                "## Preprocessing Steps",
                "- Normalize fields, handle missing values, and document units.",
                "",
                "## Problem 1 Experiments",
                "- Baseline predictive or evaluation experiment.",
                "",
                "## Problem 2 Experiments",
                "- Optimization or policy comparison experiment.",
                "",
                "## Problem 3 Experiments",
                "- Sensitivity and robustness experiment.",
                "",
                "## Metrics",
                *(f"- {metric}" for metric in metrics),
                "" if metrics else "- RMSE, MAE, normalized score, or objective value as applicable.",
                "",
                "## Expected Code Outputs",
                "- `results/problem1_results.csv`",
                "- `results/model_metrics.json`",
                "",
            ]
        )

    def _generate_decision(self, candidates_excerpt: str) -> str | None:
        if self.llm_provider is None:
            return None
        prompt = "\n".join(
            [
                "# Model Judge",
                "",
                "Select a contest-paper modeling route.",
                "Required headings: # Model Decision, ## Selected Route, "
                "## Data Requirements, ## Data Limitations, ## Figure Requirements.",
                "",
                candidates_excerpt,
            ]
        )
        result = self.llm_provider.generate("You are a strict MCM/ICM model judge.", prompt)
        content = result.content.strip()
        required = [
            "# Model Decision",
            "## Selected Route",
            "## Data Requirements",
            "## Data Limitations",
            "## Figure Requirements",
        ]
        if all(heading in content for heading in required):
            return content + "\n"
        return None

    def _diagnosis_from_candidates(self, candidates_text: str) -> ProblemDiagnosis:
        route_order = [
            ("multi_criteria_evaluation", "evaluation"),
            ("constrained_optimization", "optimization"),
            ("forecasting_model", "prediction"),
            ("monte_carlo_simulation", "simulation"),
            ("network_flow_graph", "graph_network"),
            ("multi_objective_decision", "multi_objective"),
        ]
        found_problem_types = [
            problem_type for route_id, problem_type in route_order if route_id in candidates_text
        ]
        if found_problem_types:
            return ModelingIntelligence().diagnose_problem_types(found_problem_types)
        return ProblemDiagnosis()

    def _formulation_summary(self, diagnosis: ProblemDiagnosis) -> str:
        route_ids = {route.route_id for route in diagnosis.routes}
        if "multi_criteria_evaluation" in route_ids and "constrained_optimization" in route_ids:
            return (
                "Normalize indicators into a priority score, then allocate scarce resources "
                "under capacity and budget constraints."
            )
        if "forecasting_model" in route_ids:
            return "Estimate future target values from historical observations and explanatory features."
        if "network_flow_graph" in route_ids:
            return "Represent locations as nodes and connections as weighted edges or capacities."
        return "Define task-specific objective functions after data profiling."

    def _objective_summary(self, diagnosis: ProblemDiagnosis) -> str:
        route_ids = {route.route_id for route in diagnosis.routes}
        objectives = []
        if "multi_criteria_evaluation" in route_ids:
            objectives.append("maximize transparent priority score separation")
        if "constrained_optimization" in route_ids:
            objectives.append("maximize benefit under resource constraints")
        if "forecasting_model" in route_ids:
            objectives.append("minimize forecast error")
        if "network_flow_graph" in route_ids:
            objectives.append("minimize travel cost or maximize feasible flow")
        return "; ".join(objectives) + "." if objectives else "Minimize prediction error and optimize the final decision metric."
