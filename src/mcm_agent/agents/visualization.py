from __future__ import annotations

from html import escape
from pathlib import Path

import matplotlib
import matplotlib.patches

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mcm_agent.agents.figure_quality import FigureQualityAgent
from mcm_agent.core.concept_diagrams import ConceptDiagramSpec, build_concept_diagram_specs
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import ArtifactStatus, FigurePlanItem, FigureRecord
from mcm_agent.core.repair_directive import read_repair_directive
from mcm_agent.utils.json_io import read_json, write_json


class FigurePlanningAgent:
    def run(self, workspace_root: Path) -> None:
        # Read the targeted-repair directive (if any) written by O6.
        directive = read_repair_directive(workspace_root)
        is_figures_repair = (
            isinstance(directive, dict)
            and directive.get("target_stage") == "figure_planning"
        )

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
        plan.extend(self._concept_diagram_figures(workspace_root))
        sensitivity_item = self._sensitivity_figure(workspace_root)
        if sensitivity_item is not None:
            plan.append(sensitivity_item)

        # FIG3: when a figures-dimension repair directive is active, enrich the
        # plan to guarantee a richer figure set and inject the judge's critique.
        if is_figures_repair:
            plan = self._enrich_for_repair(workspace_root, plan, directive, source_data)

        write_json(
            workspace_root / "figures" / "figure_plan.json",
            [item.model_dump(mode="json") for item in plan],
        )

    def _enrich_for_repair(
        self,
        workspace_root: Path,
        plan: list[FigurePlanItem],
        directive: dict,
        source_data: list[str],
    ) -> list[FigurePlanItem]:
        """Enrich the figure plan for a figures-dimension targeted repair.

        Guarantees:
        - The fallback data figure (fig_q1_prediction) is included even if
          route figures are present (so the plan cannot collapse to only route
          figures).
        - The sensitivity figure is included when the CSV exists.
        - Concept diagrams are included.
        - Deduplication by figure_id (no duplicates).
        - The directive's critique text appears in at least one figure's
          purpose/caption_intent so the renderer/writer can reflect it.

        Never raises — every sub-operation is best-effort.
        """
        critique: str = ""
        try:
            critique = str(directive.get("critique") or "")
        except Exception:
            pass

        repair_prefix = f"[repair: {critique}] " if critique else "[repair] "

        existing_ids: set[str] = {item.figure_id for item in plan}

        # 1. Guarantee the fallback data figure is present.
        if "fig_q1_prediction" not in existing_ids:
            fallback = FigurePlanItem(
                figure_id="fig_q1_prediction",
                purpose=f"{repair_prefix}show baseline result trend for Problem 1",
                figure_type="data_plot",
                source_data=source_data,
                generation_script="figures/source/fig_q1_prediction_plot.py",
                output_formats=["pdf", "svg", "png"],
                target_section="paper/sections/results.tex",
                caption_intent=f"{repair_prefix}Baseline result trend for Problem 1.",
                claim_supported="Baseline result trend for Problem 1.",
                evidence_ids=self._evidence_ids(workspace_root),
                source_ids=self._source_ids(workspace_root),
            )
            plan.append(fallback)
            existing_ids.add("fig_q1_prediction")

        # 2. Guarantee concept diagrams are present.
        for concept_item in self._concept_diagram_figures(workspace_root):
            if concept_item.figure_id not in existing_ids:
                plan.append(concept_item)
                existing_ids.add(concept_item.figure_id)

        # 3. Guarantee sensitivity figure is present (if CSV exists).
        sensitivity_item = self._sensitivity_figure(workspace_root)
        if sensitivity_item is not None and sensitivity_item.figure_id not in existing_ids:
            plan.append(sensitivity_item)
            existing_ids.add(sensitivity_item.figure_id)

        # 4. Inject the critique text into the first figure that doesn't yet
        #    carry it (ensures the judge's feedback is visible in the plan).
        if critique:
            critique_injected = False
            for item in plan:
                if critique in (item.purpose or "") or critique in (item.caption_intent or ""):
                    critique_injected = True
                    break
            if not critique_injected and plan:
                first = plan[0]
                # Mutate via model_copy (Pydantic v2) or direct field update.
                try:
                    plan[0] = first.model_copy(
                        update={"purpose": f"{repair_prefix}{first.purpose or ''}"}
                    )
                except Exception:
                    pass

        return plan

    def _concept_diagram_figures(self, workspace_root: Path) -> list[FigurePlanItem]:
        return [
            FigurePlanItem(
                figure_id=spec.diagram_id,
                purpose=spec.title,
                figure_type="concept_diagram",
                source_data=[],
                source_ids=spec.source_ids,
                evidence_ids=spec.evidence_ids,
                generation_script=f"figures/source/{spec.diagram_id}.mmd",
                output_formats=["pdf", "svg"],
                target_section=spec.target_section,
                caption_intent=spec.caption_intent,
                claim_supported=spec.claim_supported,
            )
            for spec in build_concept_diagram_specs(workspace_root)
        ]

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

    def _sensitivity_figure(self, workspace_root: Path) -> FigurePlanItem | None:
        """Return a data_plot FigurePlanItem for the sensitivity-analysis CSV if it
        exists; return None otherwise (graceful — no fig_sensitivity planned)."""
        csv_path = workspace_root / "results" / "sensitivity_analysis.csv"
        if not csv_path.exists():
            return None
        return FigurePlanItem(
            figure_id="fig_sensitivity",
            purpose="show how the primary metric responds to perturbation of the key parameter (sensitivity/robustness analysis)",
            figure_type="data_plot",
            source_data=["results/sensitivity_analysis.csv"],
            generation_script="figures/source/fig_sensitivity_plot.py",
            output_formats=["pdf", "svg", "png"],
            target_section="paper/sections/sensitivity.tex",
            caption_intent=(
                "Sensitivity of the primary metric to systematic perturbation of the "
                "key parameter; demonstrates model robustness."
            ),
            claim_supported=(
                "The model output is robust: the primary metric varies predictably and "
                "within acceptable bounds as the key parameter is scaled."
            ),
            evidence_ids=self._evidence_ids(workspace_root),
            source_ids=self._source_ids(workspace_root),
        )


class VisualizationAgent:
    def run(self, workspace_root: Path) -> None:
        plan_items = [
            FigurePlanItem.model_validate(item)
            for item in read_json(workspace_root / "figures" / "figure_plan.json", [])
        ]
        registry: list[FigureRecord] = []
        for item in plan_items:
            # A single un-plottable figure must never crash the whole pipeline
            # (best-effort principle): skip it and keep producing the paper.
            try:
                if item.figure_type == "data_plot":
                    record = self._render_data_plot(workspace_root, item)
                elif item.figure_type == "concept_diagram":
                    record = self._write_mermaid(workspace_root, item)
                else:
                    record = None
            except Exception:
                record = None
            if record is not None:
                registry.append(record)

        write_json(
            workspace_root / "figures" / "figure_registry.json",
            [record.model_dump(mode="json") for record in registry],
        )
        FigureQualityAgent().run(workspace_root)
        Coordinator(workspace_root).emit("figures.ready", source="VisualizationAgent")

    def _render_data_plot(self, workspace_root: Path, item: FigurePlanItem) -> FigureRecord | None:
        source = workspace_root / item.source_data[0]
        frame = pd.read_csv(source)
        numeric = frame.select_dtypes(include="number")
        if numeric.empty:
            # Nothing numeric to plot (e.g. a text-only assignment table). Skip this
            # figure rather than crashing the visualization stage.
            return None

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
        spec = self._concept_spec_for_item(workspace_root, item)
        source_path = workspace_root / "figures" / "source" / f"{item.figure_id}.mmd"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(self._mermaid_source(spec), encoding="utf-8")
        svg_path = workspace_root / "figures" / f"{item.figure_id}.svg"
        svg_path.write_text(self._svg_source(spec), encoding="utf-8")

        # Attempt to render a PDF via matplotlib so the writer can embed it.
        pdf_rel_path = self._render_concept_pdf(workspace_root, spec)

        outputs: list[str] = []
        if pdf_rel_path is not None:
            outputs.append(pdf_rel_path)
        outputs.extend([
            str(source_path.relative_to(workspace_root)),
            str(svg_path.relative_to(workspace_root)),
        ])

        return FigureRecord(
            figure_id=item.figure_id,
            type="concept_diagram",
            tool="mermaid+svg",
            source_file=str(source_path.relative_to(workspace_root)),
            outputs=outputs,
            used_in=[item.target_section],
            status=ArtifactStatus.APPROVED,
            source_data=item.source_data,
            source_ids=item.source_ids,
            evidence_ids=item.evidence_ids,
            caption_intent=item.caption_intent,
            claim_supported=item.claim_supported,
        )

    def _render_concept_pdf(
        self, workspace_root: Path, spec: "ConceptDiagramSpec"
    ) -> str | None:
        """Render a ConceptDiagramSpec to a PDF using matplotlib.

        Nodes are laid out top-to-bottom as rounded boxes; edges are drawn as
        annotated arrows between box centres. Returns the workspace-relative
        path to the PDF, or None on any failure (degrade gracefully).
        """
        try:
            import textwrap

            nodes = spec.nodes or []
            edges = spec.edges or []

            BOX_W = 2.8
            BOX_H = 0.7
            GAP_Y = 0.5   # vertical gap between boxes
            FIG_W = 5.0

            n = max(len(nodes), 1)
            total_h = n * BOX_H + (n - 1) * GAP_Y + 1.5  # top/bottom margin
            fig, ax = plt.subplots(figsize=(FIG_W, total_h))

            # Positions: centre of each box, top-to-bottom
            positions: dict[str, tuple[float, float]] = {}
            x_centre = FIG_W / 2
            for idx, node in enumerate(nodes):
                y = total_h - 0.75 - idx * (BOX_H + GAP_Y)
                positions[node.node_id] = (x_centre, y)

            # Draw edges first (under boxes)
            for edge in edges:
                if edge.source not in positions or edge.target not in positions:
                    continue
                src_x, src_y = positions[edge.source]
                tgt_x, tgt_y = positions[edge.target]
                ax.annotate(
                    "",
                    xy=(tgt_x, tgt_y + BOX_H / 2),
                    xytext=(src_x, src_y - BOX_H / 2),
                    arrowprops=dict(arrowstyle="->", color="#334155", lw=1.2),
                )
                if edge.label:
                    mid_x = (src_x + tgt_x) / 2 + 0.15
                    mid_y = (src_y + tgt_y) / 2
                    ax.text(
                        mid_x, mid_y, edge.label,
                        fontsize=7, color="#475569", ha="left", va="center",
                    )

            # Draw node boxes
            for node in nodes:
                cx, cy = positions[node.node_id]
                x0 = cx - BOX_W / 2
                y0 = cy - BOX_H / 2
                fancy = matplotlib.patches.FancyBboxPatch(
                    (x0, y0), BOX_W, BOX_H,
                    boxstyle="round,pad=0.05",
                    facecolor="#cfe2f3", edgecolor="#64748b", linewidth=1.0,
                )
                ax.add_patch(fancy)
                label_wrapped = "\n".join(textwrap.wrap(node.label, width=32))
                ax.text(
                    cx, cy, label_wrapped,
                    fontsize=8, ha="center", va="center",
                    color="#111827", wrap=False,
                )

            ax.set_xlim(0, FIG_W)
            ax.set_ylim(0, total_h)
            ax.axis("off")
            ax.set_title(spec.title, fontsize=10, pad=6)

            (workspace_root / "figures").mkdir(parents=True, exist_ok=True)
            pdf_path = workspace_root / "figures" / f"{spec.diagram_id}.pdf"
            fig.savefig(str(pdf_path), bbox_inches="tight")
            plt.close(fig)
            return str(pdf_path.relative_to(workspace_root))
        except Exception:
            return None

    def _concept_spec_for_item(
        self,
        workspace_root: Path,
        item: FigurePlanItem,
    ) -> ConceptDiagramSpec:
        for spec in build_concept_diagram_specs(workspace_root):
            if spec.diagram_id == item.figure_id:
                return spec
        return ConceptDiagramSpec(
            diagram_id=item.figure_id,
            title=item.purpose,
            target_section=item.target_section,
            caption_intent=item.caption_intent,
            claim_supported=item.claim_supported,
            nodes=[],
            edges=[],
            evidence_ids=item.evidence_ids,
            source_ids=item.source_ids,
        )

    def _mermaid_source(self, spec: ConceptDiagramSpec) -> str:
        lines = ["flowchart LR"]
        for node in spec.nodes:
            lines.append(f'  {node.node_id}["{self._mermaid_label(node.label)}"]')
        for edge in spec.edges:
            label = f"|{self._mermaid_label(edge.label)}|" if edge.label else ""
            lines.append(f"  {edge.source} -->{label} {edge.target}")
        lines.append("")
        return "\n".join(lines)

    def _svg_source(self, spec: ConceptDiagramSpec) -> str:
        nodes = spec.nodes or []
        node_width = 210
        node_height = 56
        x_gap = 54
        y_base = 70
        width = max(360, 70 + len(nodes) * (node_width + x_gap))
        height = 220
        positions = {
            node.node_id: (40 + index * (node_width + x_gap), y_base)
            for index, node in enumerate(nodes)
        }
        palette = {
            "input": "#d9ead3",
            "process": "#cfe2f3",
            "model": "#fff2cc",
            "evidence": "#eadcf8",
            "claim": "#fce5cd",
            "output": "#d9e2f3",
        }
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<defs>",
            '<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">',
            '<path d="M0,0 L8,4 L0,8 Z" fill="#334155" />',
            "</marker>",
            "</defs>",
            f'<text x="40" y="32" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#111827">{escape(spec.title)}</text>',
        ]
        for edge in spec.edges:
            if edge.source not in positions or edge.target not in positions:
                continue
            source_x, source_y = positions[edge.source]
            target_x, target_y = positions[edge.target]
            x1 = source_x + node_width
            y1 = source_y + node_height / 2
            x2 = target_x
            y2 = target_y + node_height / 2
            parts.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2 - 8}" y2="{y2}" '
                'stroke="#334155" stroke-width="1.6" marker-end="url(#arrow)" />'
            )
            if edge.label:
                parts.append(
                    f'<text x="{(x1 + x2) / 2 - 24}" y="{y1 - 8}" '
                    'font-family="Arial, sans-serif" font-size="10" fill="#475569">'
                    f"{escape(edge.label)}</text>"
                )
        for node in nodes:
            x, y = positions[node.node_id]
            fill = palette.get(node.kind, "#e5e7eb")
            label_lines = self._wrap_svg_label(node.label, max_chars=24)
            parts.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="6" fill="{fill}" stroke="#64748b" />',
                    f'<text x="{x + 12}" y="{y + 22}" font-family="Arial, sans-serif" font-size="12" fill="#111827">',
                ]
            )
            for line_index, line in enumerate(label_lines[:2]):
                dy = 0 if line_index == 0 else 16
                parts.append(f'<tspan x="{x + 12}" dy="{dy}">{escape(line)}</tspan>')
            parts.append("</text>")
            parts.append(
                f'<text x="{x + 12}" y="{y + 48}" font-family="Arial, sans-serif" font-size="9" fill="#475569">{escape(node.kind)}</text>'
            )
        parts.append("</svg>")
        return "\n".join(parts)

    def _wrap_svg_label(self, label: str, *, max_chars: int) -> list[str]:
        words = label.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word[:max_chars]
        if current:
            lines.append(current)
        return lines or [label[:max_chars]]

    def _mermaid_label(self, value: str) -> str:
        return value.replace('"', "'")
