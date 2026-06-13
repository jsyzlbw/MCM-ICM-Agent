from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mcm_agent.agents.figure_quality import FigureQualityAgent
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import ArtifactStatus, FigurePlanItem, FigureRecord
from mcm_agent.utils.json_io import read_json, write_json


class FigurePlanningAgent:
    def run(self, workspace_root: Path) -> None:
        result_candidates = sorted((workspace_root / "results").glob("*results.csv"))
        source_data = (
            [str(result_candidates[0].relative_to(workspace_root))]
            if result_candidates
            else ["results/problem1_results.csv"]
        )
        plan = self._route_data_figures(workspace_root, source_data)
        if not plan:
            plan = [
                FigurePlanItem(
                    figure_id="fig_q1_prediction",
                    purpose="show baseline result trend for Problem 1",
                    figure_type="data_plot",
                    source_data=source_data,
                    generation_script="figures/source/fig_q1_prediction_plot.py",
                    output_formats=["pdf", "svg", "png"],
                    target_section="paper/sections/results.tex",
                    caption_intent="Baseline result trend for Problem 1.",
                    claim_supported="Baseline result trend for Problem 1.",
                    evidence_ids=self._evidence_ids(workspace_root),
                    source_ids=self._source_ids(workspace_root),
                )
            ]
        plan.append(
            FigurePlanItem(
                figure_id="fig_framework",
                purpose="show the modeling workflow",
                figure_type="concept_diagram",
                source_data=[],
                generation_script="figures/source/fig_framework.mmd",
                output_formats=["svg", "pdf"],
                target_section="paper/sections/model.tex",
                caption_intent="Overview of the modeling workflow.",
                claim_supported="The paper follows a reproducible modeling workflow.",
            )
        )
        write_json(
            workspace_root / "figures" / "figure_plan.json",
            [item.model_dump(mode="json") for item in plan],
        )

    def _route_data_figures(self, workspace_root: Path, source_data: list[str]) -> list[FigurePlanItem]:
        route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
        selected_routes = route_summary.get("selected_routes", []) if isinstance(route_summary, dict) else []
        if not isinstance(selected_routes, list):
            return []
        evidence_ids = self._evidence_ids(workspace_root)
        source_ids = self._source_ids(workspace_root)
        route_specs = {
            "multi_criteria_evaluation": (
                "fig_priority_ranking",
                "show priority ranking scores across alternatives",
                "Priority ranking scores for evaluated alternatives.",
                "The evaluation route produces traceable priority rankings.",
            ),
            "constrained_optimization": (
                "fig_allocation_policy",
                "show resource allocation inputs and policy trade-offs",
                "Resource allocation policy comparison.",
                "The optimization route converts model evidence into allocation decisions.",
            ),
            "forecasting_model": (
                "fig_forecast_baseline",
                "show forecasting baseline over observations",
                "Forecasting baseline over available observations.",
                "The prediction route is supported by reproducible forecast evidence.",
            ),
            "monte_carlo_simulation": (
                "fig_scenario_robustness",
                "show scenario variability or robustness",
                "Scenario robustness under uncertain assumptions.",
                "The simulation route checks robustness against uncertain inputs.",
            ),
            "network_flow_graph": (
                "fig_network_flow",
                "show network or flow attributes",
                "Network structure or flow result summary.",
                "The graph route represents connectivity and bottlenecks.",
            ),
            "multi_objective_decision": (
                "fig_tradeoff_frontier",
                "show multi-objective trade-off structure",
                "Multi-objective trade-off summary.",
                "The decision route exposes trade-offs among competing goals.",
            ),
        }
        items = []
        for route_id in selected_routes:
            spec = route_specs.get(str(route_id))
            if spec is None:
                continue
            figure_id, purpose, caption, claim = spec
            items.append(
                FigurePlanItem(
                    figure_id=figure_id,
                    purpose=purpose,
                    figure_type="data_plot",
                    source_data=source_data,
                    generation_script=f"figures/source/{figure_id}_plot.py",
                    output_formats=["pdf", "svg", "png"],
                    target_section="paper/sections/results.tex",
                    caption_intent=caption,
                    claim_supported=claim,
                    evidence_ids=evidence_ids,
                    source_ids=source_ids,
                )
            )
        return items

    def _evidence_ids(self, workspace_root: Path) -> list[str]:
        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
        return [
            str(item.get("evidence_id"))
            for item in evidence
            if isinstance(item, dict) and item.get("evidence_id")
        ]

    def _source_ids(self, workspace_root: Path) -> list[str]:
        sources = read_json(workspace_root / "data" / "source_registry.json", [])
        return [
            str(item.get("source_id"))
            for item in sources
            if isinstance(item, dict) and item.get("source_id")
        ]


class VisualizationAgent:
    def run(self, workspace_root: Path) -> None:
        plan_items = [
            FigurePlanItem.model_validate(item)
            for item in read_json(workspace_root / "figures" / "figure_plan.json", [])
        ]
        registry: list[FigureRecord] = []
        for item in plan_items:
            if item.figure_type == "data_plot":
                registry.append(self._render_data_plot(workspace_root, item))
            elif item.figure_type == "concept_diagram":
                registry.append(self._write_mermaid(workspace_root, item))

        write_json(
            workspace_root / "figures" / "figure_registry.json",
            [record.model_dump(mode="json") for record in registry],
        )
        FigureQualityAgent().run(workspace_root)
        Coordinator(workspace_root).emit("figures.ready", source="VisualizationAgent")

    def _render_data_plot(self, workspace_root: Path, item: FigurePlanItem) -> FigureRecord:
        source = workspace_root / item.source_data[0]
        frame = pd.read_csv(source)
        numeric = frame.select_dtypes(include="number")
        if numeric.empty:
            raise ValueError(f"figure source has no numeric columns: {source}")

        plt.rcParams.update(
            {
                "figure.dpi": 160,
                "savefig.dpi": 300,
                "font.size": 9,
                "axes.titlesize": 10,
                "axes.labelsize": 9,
            }
        )
        ax = numeric.plot(marker="o", linewidth=1.4)
        ax.set_xlabel("Observation")
        ax.set_ylabel("Value")
        ax.grid(True, alpha=0.25)
        fig = ax.get_figure()

        outputs: list[str] = []
        for suffix in ["pdf", "svg", "png"]:
            output = workspace_root / "figures" / f"{item.figure_id}.{suffix}"
            fig.savefig(output, bbox_inches="tight")
            outputs.append(str(output.relative_to(workspace_root)))
        plt.close(fig)

        script_path = workspace_root / "figures" / "source" / f"{item.figure_id}_plot.py"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(
            "# Recreate this plot from the registered source data.\n",
            encoding="utf-8",
        )
        return FigureRecord(
            figure_id=item.figure_id,
            type="data_plot",
            tool="matplotlib",
            source_file=str(script_path.relative_to(workspace_root)),
            outputs=outputs,
            used_in=[item.target_section],
            status=ArtifactStatus.APPROVED,
            source_data=item.source_data,
            source_ids=item.source_ids,
            evidence_ids=item.evidence_ids,
            caption_intent=item.caption_intent,
            claim_supported=item.claim_supported,
        )

    def _write_mermaid(self, workspace_root: Path, item: FigurePlanItem) -> FigureRecord:
        source_path = workspace_root / "figures" / "source" / f"{item.figure_id}.mmd"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(
            "\n".join(
                [
                    "flowchart LR",
                    '  A["Problem"] --> B["Modeling"]',
                    '  B --> C["Data and Solver"]',
                    '  C --> D["Validation"]',
                    '  D --> E["Paper"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return FigureRecord(
            figure_id=item.figure_id,
            type="concept_diagram",
            tool="mermaid",
            source_file=str(source_path.relative_to(workspace_root)),
            outputs=[str(source_path.relative_to(workspace_root))],
            used_in=[item.target_section],
            status=ArtifactStatus.REVIEW_REQUIRED,
            source_data=item.source_data,
            source_ids=item.source_ids,
            evidence_ids=item.evidence_ids,
            caption_intent=item.caption_intent,
            claim_supported=item.claim_supported,
        )
