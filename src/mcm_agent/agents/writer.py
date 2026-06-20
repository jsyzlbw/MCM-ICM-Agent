from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from mcm_agent.agents.discussion import confirmed_language
from mcm_agent.agents.paper_context import PaperContext, build_paper_context
from mcm_agent.agents.paper_sections import render_claim_paragraph
from mcm_agent.agents.section_writer import PaperSectionWriter
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.citations import build_citation_context
from mcm_agent.core.latex_text import render_metrics_table
from mcm_agent.core.models import PaperClaimPlanItem
from mcm_agent.providers.base import TextGenerationProvider
from mcm_agent.utils.json_io import read_json


# (filename, section name, (English title, Chinese title))
SECTION_SPEC = [
    ("abstract.tex", "abstract", ("Abstract", "摘要")),
    ("introduction.tex", "introduction", ("Introduction", "引言")),
    ("assumptions.tex", "assumptions", ("Assumptions", "模型假设")),
    ("model.tex", "model", ("Model", "模型建立")),
    ("results.tex", "results", ("Results", "结果与分析")),
    ("sensitivity.tex", "sensitivity", ("Sensitivity Analysis", "敏感性分析")),
    ("conclusion.tex", "conclusion", ("Conclusion", "结论")),
]
CLAIM_BEARING = {"model.tex", "results.tex", "sensitivity.tex", "conclusion.tex"}


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
        self._language = "en"

    def run(self, workspace_root: Path) -> None:
        self._language = confirmed_language(workspace_root)
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
            figure_floats = self._embed_figures_for_section(workspace_root, filename)
            (section_dir / filename).write_text(content + figure_floats, encoding="utf-8")

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

    def _results_system_prompt(self) -> str:
        if self._language == "zh":
            return (
                "你撰写简洁、可溯源的数学建模竞赛论文。"
                "用中文撰写正文，但保留 LaTeX 命令、变量名与英文缩写。"
            )
        return "You write concise, source-traceable contest papers."

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
        result = self.llm_provider.generate(self._results_system_prompt(), prompt)
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
        """Write each section as LLM-authored LaTeX prose in the paper language.

        Visible prose comes from PaperSectionWriter; claim/evidence trace comments
        are appended (invisible) so the evidence-binding and reference stages still
        find their tokens. Results also gets a real metrics table.
        """
        zh = self._language == "zh"
        from mcm_agent.core.metrics_flatten import flatten_metrics

        # Flatten nested per-subproblem metrics for the Results table and abstract.
        metrics = flatten_metrics(read_json(workspace_root / "results" / "model_metrics.json", {}))
        by_section: dict[str, list[PaperClaimPlanItem]] = defaultdict(list)
        for claim in claim_plan:
            by_section[Path(claim.section).name].append(claim)
            if claim.status == "unresolved":
                self._append_unresolved_claim(workspace_root, claim)

        from mcm_agent.core.model_spec import read_model_spec

        model_spec = read_model_spec(workspace_root)
        sensitivity = self._read_sensitivity(workspace_root)
        citation_context = build_citation_context(workspace_root)
        writer = PaperSectionWriter(self.llm_provider, self._language)
        for filename, name, (en_title, zh_title) in SECTION_SPEC:
            title = zh_title if zh else en_title
            claims = by_section.get(filename, [])
            facts = self._facts_for_section(name, context, metrics, claims, model_spec, sensitivity)
            body = writer.write_section(name, title, facts)
            extras = self._section_extras(
                filename, name, metrics, claims, zh, citation_context, sensitivity
            )
            figure_floats = self._embed_figures_for_section(workspace_root, filename)
            (section_dir / filename).write_text(body + extras + figure_floats, encoding="utf-8")

    def _model_facts_from_spec(self, model_spec: object, claim_texts: list[str]) -> dict[str, object]:
        """Model-section facts straight from the designed ModelSpec, so the narrative
        matches the spec the solver implemented (model<->code<->narrative coherence)."""
        subs = []
        extra_lines: list[str] = []
        for sub in model_spec.subproblems:  # type: ignore[attr-defined]
            subs.append(
                {
                    "title": sub.title,
                    "approach": sub.approach,
                    "variables": [{"symbol": v.symbol, "meaning": v.meaning} for v in sub.variables],
                    "assumptions": sub.assumptions,
                    "equations": sub.equations,
                    "algorithm_steps": sub.algorithm_steps,
                    "metrics": sub.metrics,
                }
            )
            extra_lines.append(f"{sub.title}（{sub.approach}）" if self._language == "zh" else f"{sub.title} ({sub.approach})")
            extra_lines.extend(sub.assumptions)
            extra_lines.extend(sub.algorithm_steps)
        return {"model_spec": subs, "claims": claim_texts, "extra_lines": extra_lines}

    def _facts_for_section(
        self,
        name: str,
        context: PaperContext,
        metrics: dict[str, object],
        claims: list[PaperClaimPlanItem],
        model_spec: object = None,
        sensitivity: dict | None = None,
    ) -> dict[str, object]:
        top_metrics = dict(list(metrics.items())[:6])
        claim_texts = [c.claim_text for c in claims if c.status != "unresolved" and c.claim_text]
        if name == "model" and model_spec is not None and model_spec.subproblems:
            # The spec is the model now: drop the canned "selected model route" claim so
            # the narrative describes the designed spec, not a leaked catalog route.
            spec_claims = [
                c.claim_text
                for c in claims
                if c.status != "unresolved" and c.claim_text and c.claim_type != "model_choice"
            ]
            return self._model_facts_from_spec(model_spec, spec_claims)
        if name == "abstract":
            # When a ModelSpec is available, derive the approach phrase from the
            # spec (same source as the model section) so that abstract and model
            # section describe the *same* method (coherence).  Fall back to
            # model_decision_summary for runs that pre-date the spec.
            if model_spec is not None and getattr(model_spec, "subproblems", None):
                approach_parts = [
                    (
                        f"{sub.title}（{sub.approach}）"
                        if self._language == "zh"
                        else f"{sub.title} ({sub.approach})"
                    )
                    for sub in model_spec.subproblems
                    if sub.approach
                ]
                approach = "; ".join(approach_parts) if approach_parts else context.model_decision_summary[:600]
            else:
                approach = context.model_decision_summary[:600]
            return {
                "problem": context.problem_summary,
                "approach": approach,
                "key_metrics": top_metrics,
            }
        if name == "introduction":
            return {
                "problem": context.problem_summary,
                "research_direction": context.direction_summary[:400],
                "claims": claim_texts,
            }
        if name == "assumptions":
            return {"problem": context.problem_summary, "claims": claim_texts}
        if name == "model":
            return {
                "model_decision": context.model_decision_summary,
                "routes": context.selected_routes,
                "claims": claim_texts,
            }
        if name == "results":
            # Results is table-driven (real metrics); claim texts excluded to avoid
            # leaking underscored metric names / robotic per-metric sentences.
            return {
                "metrics": metrics,
                "instruction": "Interpret each metric and whether it indicates a good fit.",
            }
        if name == "sensitivity":
            facts: dict[str, object] = {
                "validation": context.validation_summary[:600],
                "claims": claim_texts,
            }
            if sensitivity and sensitivity.get("rows"):
                facts["sensitivity_table"] = {
                    "header": sensitivity["header"],
                    "rows": sensitivity["rows"][:8],
                }
            return facts
        if name == "conclusion":
            return {
                "problem": context.problem_summary,
                "key_metrics": dict(list(metrics.items())[:4]),
                "routes": context.selected_routes,
                "claims": claim_texts,
            }
        return {}

    def _section_extras(
        self,
        filename: str,
        name: str,
        metrics: dict[str, object],
        claims: list[PaperClaimPlanItem],
        zh: bool,
        citation_context: object,
        sensitivity: dict | None = None,
    ) -> str:
        parts: list[str] = []
        if name == "results" and metrics:
            caption = "模型指标" if zh else "Model metrics"
            parts.append(
                "\n\\begin{table}[h]\n\\centering\n"
                + render_metrics_table(metrics, self._language)
                + f"\n\\caption{{{caption}}}\n\\end{{table}}"
            )
        if name == "sensitivity" and sensitivity and sensitivity.get("rows"):
            caption = "敏感性分析" if zh else "Sensitivity analysis"
            parts.append(
                "\n\\begin{table}[h]\n\\centering\n"
                + self._render_sensitivity_table(sensitivity)
                + f"\n\\caption{{{caption}}}\n\\end{{table}}"
            )
        # Visible citation anchor so referenced sources appear in the bibliography.
        source_ids: list[str] = []
        for claim in claims:
            source_ids.extend(claim.source_ids)
        cite = citation_context.cite_command(source_ids) if source_ids else ""
        if cite:
            parts.append((f"（来源：{cite}）" if zh else f"(Sources: {cite})"))
        trace = self._section_trace(claims)
        if not trace and filename in CLAIM_BEARING:
            trace = "% claim_id=section_baseline evidence_id=missing figure_id=missing source_id=missing"
        if trace:
            parts.append(trace)
        return ("\n" + "\n".join(parts) + "\n") if parts else "\n"

    def _read_sensitivity(self, workspace_root: Path) -> dict | None:
        path = workspace_root / "results" / "sensitivity_analysis.csv"
        if not path.exists():
            return None
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) < 2:
            return None
        header = [cell.strip() for cell in lines[0].split(",")]
        rows = [
            [cell.strip() for cell in line.split(",")]
            for line in lines[1:]
            if line.split(",")[0].strip().lower() != "baseline"
        ]
        return {"header": header, "rows": rows} if rows else None

    def _render_sensitivity_table(self, sensitivity: dict) -> str:
        from mcm_agent.core.latex_text import latex_escape_text

        header = sensitivity["header"]
        cols = "l" * len(header)
        head_row = " & ".join(latex_escape_text(str(h)) for h in header) + " \\\\"
        body_rows = [
            " & ".join(latex_escape_text(str(c)) for c in row) + " \\\\"
            for row in sensitivity["rows"][:10]
        ]
        return "\n".join(
            ["\\begin{tabular}{" + cols + "}", "\\toprule", head_row, "\\midrule", *body_rows, "\\bottomrule", "\\end{tabular}"]
        )

    def _section_trace(self, claims: list[PaperClaimPlanItem]) -> str:
        lines = []
        for claim in claims:
            evidence_id = claim.evidence_ids[0] if claim.evidence_ids else "missing"
            figure_id = claim.figure_ids[0] if claim.figure_ids else "missing"
            source_id = claim.source_ids[0] if claim.source_ids else "missing"
            lines.append(
                self._claim_trace_comment(claim.claim_id, evidence_id, figure_id, source_id)
            )
        return "\n".join(lines)

    def _claim_plan_paragraph(self, workspace_root: Path, claim: PaperClaimPlanItem) -> str:
        if claim.status == "unresolved":
            self._append_unresolved_claim(workspace_root, claim)
        return render_claim_paragraph(claim, build_citation_context(workspace_root))

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

    def _figure_float(self, figure_id: str, caption: str, output_path: str) -> str:
        """Return a LaTeX figure float string for a given figure id and caption.

        *output_path* is the workspace-relative path to the rendered file
        (e.g. 'figures/fig_q1.pdf').  We strip the 'figures/' prefix so that
        with \\graphicspath{{../figures/}{figures/}} the path resolves both when
        compiling from paper/ and from the workspace root.
        """
        escaped_caption = caption.replace("_", "\\_")
        # Strip any leading 'figures/' prefix — graphicspath handles the directory.
        include_path = output_path
        for prefix in ("figures/", "../figures/"):
            if include_path.startswith(prefix):
                include_path = include_path[len(prefix):]
                break
        return (
            "\n\\begin{figure}[htbp]\n"
            "\\centering\n"
            f"\\includegraphics[width=0.85\\linewidth]{{{include_path}}}\n"
            f"\\caption{{{escaped_caption}}}\n"
            f"\\label{{fig:{figure_id}}}\n"
            "\\end{figure}\n"
        )

    def _best_output(self, outputs: list[str], workspace_root: Path) -> str | None:
        """Return the best output path for pdflatex/tectonic includegraphics.

        Only PDF and PNG are reliably includable without extra packages; we
        prefer PDF, then PNG.  SVG and .mmd are skipped because tectonic does
        not natively include SVG via \\includegraphics.
        """
        for ext in (".pdf", ".png"):
            for o in outputs:
                if o.endswith(ext) and (workspace_root / o).exists():
                    return o
        return None

    def _embed_figures_for_section(
        self, workspace_root: Path, section_filename: str
    ) -> str:
        """Return LaTeX figure floats for all registry figures whose used_in
        matches *section_filename*.  Returns empty string if no registry or no match."""
        figures = read_json(workspace_root / "figures" / "figure_registry.json", [])
        if not isinstance(figures, list):
            return ""
        floats: list[str] = []
        for record in figures:
            if not isinstance(record, dict):
                continue
            figure_id = str(record.get("figure_id", "")).strip()
            if not figure_id:
                continue
            used_in = record.get("used_in", [])
            if not isinstance(used_in, list):
                continue
            # used_in entries look like "paper/sections/results.tex"
            # section_filename looks like "results.tex"
            matches = any(
                Path(u).name == section_filename for u in used_in
            )
            if not matches:
                continue
            outputs = record.get("outputs", [])
            if not isinstance(outputs, list):
                outputs = []
            output_path = self._best_output(outputs, workspace_root)
            if output_path is None:
                # No includable file on disk (e.g. SVG/mmd-only) — skip gracefully.
                continue
            caption = str(record.get("caption_intent", "")).strip() or figure_id
            floats.append(self._figure_float(figure_id, caption, output_path))
        return "".join(floats)

    def _write_main_files(self, paper_dir: Path) -> None:
        # Empty by default; ReferenceManager fills real entries (and prunes the
        # bibliography from main.tex when there are no registered sources).
        references = paper_dir / "references.bib"
        if not references.exists():
            references.write_text("", encoding="utf-8")
        section_dir = paper_dir / "sections"
        section_text = ""
        if section_dir.exists():
            for tex in sorted(section_dir.glob("*.tex")):
                section_text += tex.read_text(encoding="utf-8")
        # Also scan summary_sheet.tex for CJK detection
        summary_sheet_path = paper_dir / "summary_sheet.tex"
        if summary_sheet_path.exists():
            section_text += summary_sheet_path.read_text(encoding="utf-8")
        # CJK content needs a XeTeX/CJK-capable class; tectonic auto-fetches the
        # ctex Fandol fonts. English-only papers stay on plain article.
        has_cjk = any("一" <= ch <= "鿿" for ch in section_text)
        document_class = "ctexart" if has_cjk else "article"
        preamble = [
            f"\\documentclass[12pt]{{{document_class}}}",
            "\\usepackage{graphicx}",
            "\\usepackage{amsmath}",
            "\\usepackage{booktabs}",
            "\\graphicspath{{../figures/}{figures/}}",
        ]
        # summary_sheet is included first (before all body sections) if the file
        # exists; this gives judges the required one-page summary as page 1.
        summary_input = (
            ["\\input{summary_sheet}"]
            if summary_sheet_path.exists()
            else []
        )
        body = [
            "\\begin{document}",
            *summary_input,
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
        (paper_dir / "main.tex").write_text("\n".join(preamble + body), encoding="utf-8")

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
