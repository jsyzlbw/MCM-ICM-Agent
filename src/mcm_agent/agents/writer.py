from __future__ import annotations

from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
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

        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
        figures = read_json(workspace_root / "figures" / "figure_registry.json", [])
        sources = read_json(workspace_root / "data" / "source_registry.json", [])
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
        section_content["model.tex"] = self._fallback_model_section(route_summary)
        generated_results = self._generate_results_section(evidence, figures, sources)
        if generated_results is not None:
            section_content["results.tex"] = generated_results
        else:
            section_content["results.tex"] = self._fallback_results_section(evidence, figures, sources)

        for filename, content in section_content.items():
            (section_dir / filename).write_text(content, encoding="utf-8")

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
        return (
            "\\section{Results}\n"
            "Validated evidence items support the numerical claims in this section. "
            f"The primary trace links are evidence_id={evidence_id}, "
            f"figure_id={figure_id}, and source_id={source_id}.\n"
        )

    def _fallback_model_section(self, route_summary: object) -> str:
        if not isinstance(route_summary, dict):
            return SECTION_CONTENT["model.tex"]
        routes = route_summary.get("selected_routes", [])
        metrics = route_summary.get("route_metrics", {})
        if not isinstance(routes, list) or not routes:
            return SECTION_CONTENT["model.tex"]
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

    def _latex_escape(self, value: str) -> str:
        return value.replace("_", "\\_")
