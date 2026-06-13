from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
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
            ),
            FigurePlanItem(
                figure_id="fig_framework",
                purpose="show the modeling workflow",
                figure_type="concept_diagram",
                source_data=[],
                generation_script="figures/source/fig_framework.mmd",
                output_formats=["svg", "pdf"],
                target_section="paper/sections/model.tex",
                caption_intent="Overview of the modeling workflow.",
            ),
        ]
        write_json(
            workspace_root / "figures" / "figure_plan.json",
            [item.model_dump(mode="json") for item in plan],
        )


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
        figure_issues = self._figure_gate_issues(registry)
        record_gate_decision(
            workspace_root,
            "figure_gate.json",
            GateDecision(
                gate_id="figure_quality_gate",
                status="fail" if figure_issues else "pass",
                failure_reason="visual_or_vector_issue" if figure_issues else None,
                repair_stage="figure_planning" if figure_issues else None,
                blocking_findings=figure_issues,
            ),
        )
        Coordinator(workspace_root).emit("figures.ready", source="VisualizationAgent")

    def _figure_gate_issues(self, registry: list[FigureRecord]) -> list[str]:
        issues: list[str] = []
        for record in registry:
            if record.type == "data_plot":
                has_vector = any(output.endswith((".pdf", ".svg")) for output in record.outputs)
                if not has_vector:
                    issues.append(f"Data figure `{record.figure_id}` has no PDF/SVG output.")
            if record.status == ArtifactStatus.REJECTED:
                issues.append(f"Figure `{record.figure_id}` is rejected.")
        return issues

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
        )
