from __future__ import annotations

from pathlib import Path

from mcm_agent.agents.paper_context import PaperContext, build_paper_context
from mcm_agent.agents.paper_sections import render_claim_paragraph, render_claim_plan_sections
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import PaperClaimPlanItem
from mcm_agent.providers.base import TextGenerationProvider
from mcm_agent.utils.json_io import read_json


SECTION_CONTENT = {
    "abstract.tex": "\\section*{Abstract}\nThis paper presents an evidence-backed modeling workflow.\n",
    "introduction.tex": "\\section{Introduction}\nWe analyze the problem using structured decomposition and reproducible experiments.\n",
    "assumptions.tex": "\\section{Assumptions}\nRegistered evidence and validated code outputs define the factual basis of the paper.\n",
    "model.tex": "\\section{Model}\nThe selected model route balances interpretability, feasibility, and paper clarity.\n",
    "results.tex": "\\section{Results}\nValidated evidence items support the numerical claims in this section.\n",
    "sensitivity.tex": "\\section{Sensitivity Analysis}\nRobustness is checked with baseline sensitivity analysis.\n",
    "conclusion.tex": "\\section{Conclusion}\nThe workflow produces traceable and reviewable contest submission artifacts.\n",
}


class PaperWriterAgent:
    def __init__(self, llm_provider: TextGenerationProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run(self, workspace_root: Path) -> None:
        paper_dir = workspace_root / "paper"
        section_dir = paper_dir / "sections"
        section_dir.mkdir(parents=True, exist_ok=True)

        claim_plan = self._read_claim_plan(workspace_root)
        if claim_plan:
            self._write_claim_plan_sections(
                workspace_root,
                section_dir,
                claim_plan,
                build_paper_context(workspace_root),
            )
            self._write_main_files(paper_dir)
            Coordinator(workspace_root).emit(
                "paper.draft.ready",
                payload={"artifact_ids": ["paper_draft_v1"]},
                source="PaperWriterAgent",
            )
            return

        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
        figures = read_json(workspace_root / "figures" / "figure_registry.json", [])
        sources = read_json(workspace_root / "data" / "source_registry.json", [])
        evidence_id = self._first_id(evidence, "evidence_id")
        figure_id = self._first_id(figures, "figure_id")
        source_id = self._first_id(sources, "source_id")
        route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
        unresolved_path = workspace_root / "unresolved_issues.md"
        if not evidence:
            unresolved_path.write_text(
                unresolved_path.read_text(encoding="utf-8")
                + "[[UNRESOLVED:\n"
                + 'reason = "No verified evidence available for paper writing"\n'
                + 'needed_input = "Run SolverCoderAgent and ValidationAgent"\n'
                + 'affected_section = "paper/sections/results.tex"\n'
                + "]]\n",
                encoding="utf-8",
            )

        section_content = dict(SECTION_CONTENT)
        section_content["model.tex"] = self._fallback_model_section(
            route_summary,
            evidence_id,
            figure_id,
            source_id,
        )
        generated_results = self._generate_results_section(evidence, figures, sources)
        if generated_results is not None:
            section_content["results.tex"] = generated_results
        else:
            section_content["results.tex"] = self._fallback_results_section(evidence, figures, sources)
        section_content["sensitivity.tex"] = self._fallback_sensitivity_section(
            route_summary,
            evidence_id,
            figure_id,
            source_id,
        )
        section_content["conclusion.tex"] = self._fallback_conclusion_section(
            evidence_id,
            figure_id,
            source_id,
        )

        for filename, content in section_content.items():
            (section_dir / filename).write_text(content, encoding="utf-8")

        self._write_main_files(paper_dir)
        Coordinator(workspace_root).emit(
            "paper.draft.ready",
            payload={"artifact_ids": ["paper_draft_v1"]},
            source="PaperWriterAgent",
        )

    def _fallback_results_section(
        self,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> str:
        evidence_id = self._first_id(evidence, "evidence_id")
        figure_id = self._first_id(figures, "figure_id")
        source_id = self._first_id(sources, "source_id")
        evidence_lines = []
        for item in evidence[:5]:
            evidence_lines.append(
                "- Evidence "
                + self._texttt(str(item.get("evidence_id", "missing")))
                + " supports: "
                + self._latex_escape(str(item.get("claim", "registered model claim")))
                + "."
            )
        figure_lines = []
        for item in figures[:5]:
            figure_lines.append(
                "- Figure "
                + self._texttt(str(item.get("figure_id", "missing")))
                + " is used for "
                + self._latex_escape(str(item.get("caption_intent", "registered result figure")))
                + "."
            )
        source_comment = f"% source_id={source_id}"
        evidence_comment = f"% evidence_id={evidence_id}"
        figure_comment = f"% figure_id={figure_id}"
        claim_comment = self._claim_trace_comment(
            "claim_results_primary",
            evidence_id,
            figure_id,
            source_id,
        )
        return "\n".join(
            [
                "\\section{Results}",
                "The reported results are restricted to registered evidence, figures, and sources. "
                "The primary trace links are "
                f"evidence {self._texttt(evidence_id)}, figure {self._texttt(figure_id)}, "
                f"and source {self._texttt('source_id=' + source_id)}.",
                evidence_comment,
                figure_comment,
                source_comment,
                claim_comment,
                "",
                "\\subsection{Evidence Trace}",
                *(evidence_lines or ["- No verified evidence was available at drafting time."]),
                "",
                "\\subsection{Figure Trace}",
                *(figure_lines or ["- No registered figure was available at drafting time."]),
                "",
            ]
        )

    def _fallback_model_section(
        self,
        route_summary: object,
        evidence_id: str = "missing",
        figure_id: str = "missing",
        source_id: str = "missing",
    ) -> str:
        if not isinstance(route_summary, dict):
            return self._with_trace_comments(
                SECTION_CONTENT["model.tex"],
                evidence_id,
                figure_id,
                source_id,
                claim_id="claim_model_route",
            )
        routes = route_summary.get("selected_routes", [])
        metrics = route_summary.get("route_metrics", {})
        if not isinstance(routes, list) or not routes:
            return self._with_trace_comments(
                SECTION_CONTENT["model.tex"],
                evidence_id,
                figure_id,
                source_id,
                claim_id="claim_model_route",
            )
        route_text = " + ".join(self._latex_escape(str(route)) for route in routes)
        metric_parts = []
        if isinstance(metrics, dict):
            for metric_name, payload in metrics.items():
                if isinstance(payload, dict) and "value" in payload:
                    metric_parts.append(
                        f"{self._latex_escape(str(metric_name))}={self._latex_escape(str(payload['value']))}"
                    )
        metric_sentence = (
            " The route-specific implementation metrics are "
            + ", ".join(metric_parts)
            + "."
            if metric_parts
            else ""
        )
        return (
            "\\section{Model}\n"
            f"The selected route is {route_text}. "
            "This route is chosen because it binds the problem diagnosis to reproducible "
            f"code outputs and later figure planning.{metric_sentence}\n"
            f"% evidence_id={evidence_id}\n"
            f"% figure_id={figure_id}\n"
            f"% source_id={source_id}\n"
            + self._claim_trace_comment(
                "claim_model_route",
                evidence_id,
                figure_id,
                source_id,
            )
            + "\n"
        )

    def _fallback_sensitivity_section(
        self,
        route_summary: object,
        evidence_id: str = "missing",
        figure_id: str = "missing",
        source_id: str = "missing",
    ) -> str:
        if not isinstance(route_summary, dict):
            return self._with_trace_comments(
                SECTION_CONTENT["sensitivity.tex"],
                evidence_id,
                figure_id,
                source_id,
                claim_id="claim_sensitivity_baseline",
            )
        metrics = route_summary.get("route_metrics", {})
        metric_lines = []
        if isinstance(metrics, dict):
            for metric_name, payload in metrics.items():
                if isinstance(payload, dict) and "value" in payload:
                    metric_lines.append(
                        "- "
                        + self._texttt(
                            f"{str(metric_name)}={str(payload['value'])}"
                        )
                        + " is treated as a baseline sensitivity anchor."
                    )
        return "\n".join(
            [
                "\\section{Sensitivity Analysis}",
                "Sensitivity analysis focuses on the registered route-specific metrics, "
                "so reviewers can trace robustness claims back to code outputs.",
                f"% evidence_id={evidence_id}",
                f"% figure_id={figure_id}",
                f"% source_id={source_id}",
                self._claim_trace_comment(
                    "claim_sensitivity_baseline",
                    evidence_id,
                    figure_id,
                    source_id,
                ),
                "",
                *(metric_lines or ["- No route-specific metric was available for sensitivity analysis."]),
                "",
            ]
        )

    def _fallback_conclusion_section(
        self,
        evidence_id: str = "missing",
        figure_id: str = "missing",
        source_id: str = "missing",
    ) -> str:
        return self._with_trace_comments(
            SECTION_CONTENT["conclusion.tex"],
            evidence_id,
            figure_id,
            source_id,
            claim_id="claim_conclusion_traceability",
        )

    def _generate_results_section(
        self,
        evidence: list[dict[str, object]],
        figures: list[dict[str, object]],
        sources: list[dict[str, object]],
    ) -> str | None:
        if self.llm_provider is None:
            return None
        evidence_id = self._first_id(evidence, "evidence_id")
        figure_id = self._first_id(figures, "figure_id")
        source_id = self._first_id(sources, "source_id")
        prompt = "\n".join(
            [
                "# Paper Writer",
                "",
                "Draft only the LaTeX Results section for an MCM/ICM paper.",
                "Required: include \\section{Results}, evidence_id, figure_id, and source_id.",
                f"evidence_id={evidence_id}",
                f"figure_id={figure_id}",
                f"source_id={source_id}",
            ]
        )
        result = self.llm_provider.generate("You write concise, source-traceable contest papers.", prompt)
        content = result.content.strip()
        if (
            "\\section{Results}" in content
            and f"evidence_id={evidence_id}" in content
            and f"figure_id={figure_id}" in content
            and f"source_id={source_id}" in content
        ):
            return content + "\n"
        return None

    def _first_id(self, rows: list[dict[str, object]], key: str) -> str:
        if not rows:
            return "missing"
        value = rows[0].get(key)
        return str(value) if value else "missing"

    def _read_claim_plan(self, workspace_root: Path) -> list[PaperClaimPlanItem]:
        rows = read_json(workspace_root / "paper" / "claim_plan.json", [])
        if not isinstance(rows, list):
            return []
        return [
            PaperClaimPlanItem.model_validate(row)
            for row in rows
            if isinstance(row, dict)
        ]

    def _write_claim_plan_sections(
        self,
        workspace_root: Path,
        section_dir: Path,
        claim_plan: list[PaperClaimPlanItem],
        context: PaperContext,
    ) -> None:
        for claim in claim_plan:
            if claim.status == "unresolved":
                self._append_unresolved_claim(workspace_root, claim)
        section_content = render_claim_plan_sections(claim_plan, context)
        for filename, content in section_content.items():
            (section_dir / filename).write_text(content, encoding="utf-8")

    def _claim_plan_paragraph(self, workspace_root: Path, claim: PaperClaimPlanItem) -> str:
        if claim.status == "unresolved":
            self._append_unresolved_claim(workspace_root, claim)
        return render_claim_paragraph(claim)

    def _append_unresolved_claim(self, workspace_root: Path, claim: PaperClaimPlanItem) -> None:
        path = workspace_root / "unresolved_issues.md"
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(
            current
            + "[[UNRESOLVED:\n"
            + f'reason = "{claim.unresolved_reason}"\n'
            + f'needed_input = "Resolve planned claim {claim.claim_id}"\n'
            + f'affected_section = "{claim.section}"\n'
            + "]]\n",
            encoding="utf-8",
        )

    def _write_main_files(self, paper_dir: Path) -> None:
        (paper_dir / "references.bib").write_text(
            "@misc{registered_sources,\n  title={Registered data sources},\n  year={2026}\n}\n",
            encoding="utf-8",
        )
        (paper_dir / "main.tex").write_text(
            "\n".join(
                [
                    "\\documentclass[12pt]{article}",
                    "\\usepackage{graphicx}",
                    "\\usepackage{amsmath}",
                    "\\usepackage{booktabs}",
                    "\\begin{document}",
                    "\\input{sections/abstract}",
                    "\\input{sections/introduction}",
                    "\\input{sections/assumptions}",
                    "\\input{sections/model}",
                    "\\input{sections/results}",
                    "\\input{sections/sensitivity}",
                    "\\input{sections/conclusion}",
                    "\\bibliographystyle{plain}",
                    "\\bibliography{references}",
                    "\\end{document}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _with_trace_comments(
        self,
        content: str,
        evidence_id: str,
        figure_id: str,
        source_id: str,
        *,
        claim_id: str | None = None,
    ) -> str:
        traced = (
            content.rstrip()
            + "\n"
            + f"% evidence_id={evidence_id}\n"
            + f"% figure_id={figure_id}\n"
            + f"% source_id={source_id}\n"
        )
        if claim_id is None:
            return traced
        return traced + self._claim_trace_comment(claim_id, evidence_id, figure_id, source_id) + "\n"

    def _claim_trace_comment(
        self,
        claim_id: str,
        evidence_id: str,
        figure_id: str,
        source_id: str,
    ) -> str:
        return (
            f"% claim_id={claim_id} "
            f"evidence_id={evidence_id} "
            f"figure_id={figure_id} "
            f"source_id={source_id}"
        )

    def _latex_escape(self, value: str) -> str:
        return value.replace("_", "\\_")

    def _texttt(self, value: str) -> str:
        return "\\texttt{" + self._latex_escape(value) + "}"
