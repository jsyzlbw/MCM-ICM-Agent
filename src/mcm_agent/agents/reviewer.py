from __future__ import annotations

import re
from pathlib import Path

from mcm_agent.agents.discussion import confirmed_language
from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.core.lineage import find_unbound_external_data
from mcm_agent.core.models import PaperClaimPlanItem
from mcm_agent.providers.base import TextGenerationProvider
from mcm_agent.utils.json_io import read_json, write_json


# Language-keyed strings for the deterministic fallback report.
# Each entry: (English text, Chinese text)
_REVIEW_STRINGS: dict[str, tuple[str, str]] = {
    "h1": ("# Automatic Review Report", "# 自动评审报告"),
    "h2_score": ("## Overall Score", "## 总体评分"),
    "h2_strengths": ("## Key Strengths", "## 主要优点"),
    "h2_risks": ("## High-Risk Issues", "## 高风险问题"),
    "h2_revisions": ("## Required Revisions", "## 需要修改的问题"),
    "h2_award": ("## Award-Impact Issues", "## 可能影响奖项的问题"),
    "h2_suggestions": ("## Revision Suggestions", "## 修改建议"),
    "status_pass": ("Pass with comments.", "通过，有意见。"),
    "status_blocked": ("Blocked.", "已阻断。"),
    "strength_workflow": (
        "The workflow records evidence, figures, and review artifacts.",
        "工作流已记录证据、图表和评审产物。",
    ),
    "revision_review": (
        "Review all generated sections before submission.",
        "提交前请逐节审查所有生成内容。",
    ),
    "award_modeling": (
        "Missing deep domain-specific modeling may affect competitiveness.",
        "缺乏深入的领域建模可能影响竞争力。",
    ),
    "suggestion_figures": (
        "Improve model-specific explanation and figure captions.",
        "完善模型专属说明及图表标题。",
    ),
    "none": ("None.", "无。"),
    # headings used for _generate_review validation
    "required_h1": ("# Automatic Review Report", "# 自动评审报告"),
    "required_h2_score": ("## Overall Score", "## 总体评分"),
    "required_h2_risks": ("## High-Risk Issues", "## 高风险问题"),
    "required_h2_suggestions": ("## Revision Suggestions", "## 修改建议"),
}


SOURCE_ID_PATTERN = re.compile(r"source_id=([A-Za-z0-9_-]+)")
PLACEHOLDER_SOURCE_IDS = {"missing", "none", "unknown"}
REQUIRED_PAPER_SECTIONS = {
    "abstract.tex",
    "introduction.tex",
    "assumptions.tex",
    "model.tex",
    "results.tex",
    "sensitivity.tex",
    "conclusion.tex",
}


class ReviewerAgent:
    def __init__(self, llm_provider: TextGenerationProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run(self, workspace_root: Path) -> None:
        unresolved = (workspace_root / "unresolved_issues.md").read_text(encoding="utf-8")
        fact_report = workspace_root / "review" / "fact_regression_report.md"
        fact_text = fact_report.read_text(encoding="utf-8") if fact_report.exists() else ""
        blocking: list[str] = []
        if "[[UNRESOLVED:" in unresolved:
            blocking.append("Unresolved placeholders remain.")
        if "critical" in fact_text:
            blocking.append("Critical fact regression remains.")
        unbound_sources = find_unbound_external_data(workspace_root)
        if unbound_sources:
            blocking.append("External data sources are missing data lineage.")
        missing_references = self._missing_references(workspace_root)
        if missing_references:
            blocking.append(
                "External data sources are missing from references: "
                + ", ".join(f"`{source_id}`" for source_id in missing_references)
                + "."
            )
        missing_paper_bindings, has_omitted_planned_claim = (
            self._paper_binding_failure_reason(workspace_root)
        )
        if missing_paper_bindings:
            blocking.append(
                "Paper claims are missing evidence bindings: "
                + ", ".join(f"`{section}`" for section in missing_paper_bindings)
                + "."
            )
        unresolved_critical_claims = self._unresolved_critical_claims(workspace_root)
        if unresolved_critical_claims:
            blocking.append(
                "Critical planned claims remain unresolved: "
                + ", ".join(f"`{claim_id}`" for claim_id in unresolved_critical_claims)
                + "."
            )
        quality_scores = self._score_paper_quality(workspace_root)
        write_json(workspace_root / "review" / "paper_quality_scores.json", quality_scores)
        if quality_scores["status"] == "fail":
            blocking.append("Paper section completeness is too low.")
        typesetting_quality = self._typesetting_quality_failure(workspace_root)
        if typesetting_quality:
            blocking.extend(typesetting_quality["blocking_findings"])
        self._write_source_audit_report(workspace_root, unbound_sources)

        language = confirmed_language(workspace_root)
        reviewer_report = (
            self._generate_review(blocking, language=language)
            or self._fallback_review(blocking, language=language)
        )
        (workspace_root / "review" / "reviewer_report.md").write_text(
            reviewer_report,
            encoding="utf-8",
        )
        (workspace_root / "review" / "methodology_checklist_report.md").write_text(
            "\n".join(
                [
                    "# Methodology Checklist Report",
                    "",
                    "## Macro Logic",
                    "- Check problem to model to result chain.",
                    "",
                    "## Writing Details",
                    "- Remove generic filler.",
                    "",
                    "## English Expression",
                    "- Keep academic but natural phrasing.",
                    "",
                    "## LaTeX Formatting",
                    "- Check references, figures, and page layout.",
                    "",
                    "## Figure Quality",
                    "- Ensure data source is registered for every data figure.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        failure_reason = None
        repair_stage = None
        if unbound_sources:
            failure_reason = "bad_data"
            repair_stage = "search_data"
        elif missing_references:
            failure_reason = "bad_data"
            repair_stage = "paper_writer"
        elif unresolved_critical_claims:
            failure_reason = "bad_results"
            repair_stage = "solver_coder"
        elif has_omitted_planned_claim:
            failure_reason = "bad_writing"
            repair_stage = "paper_writer"
        elif missing_paper_bindings:
            failure_reason = "bad_writing"
            repair_stage = "paper_writer"
        elif quality_scores["status"] == "fail":
            failure_reason = "bad_writing"
            repair_stage = "paper_writer"
        elif typesetting_quality:
            failure_reason = "format_issue"
            repair_stage = typesetting_quality["repair_stage"]
        elif blocking:
            failure_reason = "bad_writing"
            repair_stage = "paper_writer"
        record_gate_decision(
            workspace_root,
            "final_gate.json",
            GateDecision(
                gate_id="final_gatekeeper",
                status="fail" if blocking else "pass",
                failure_reason=failure_reason,
                repair_stage=repair_stage,
                blocking_findings=blocking,
            ),
        )
        Coordinator(workspace_root).emit(
            "paper.review.failed" if blocking else "paper.review.passed",
            source="ReviewerAgent",
        )

    def _typesetting_quality_failure(self, workspace_root: Path) -> dict[str, object] | None:
        report = read_json(workspace_root / "review" / "typesetting_quality.json", {})
        if not isinstance(report, dict) or report.get("status") != "fail":
            return None
        findings = report.get("blocking_findings")
        blocking_findings = [
            str(finding)
            for finding in findings
            if isinstance(finding, str) and finding.strip()
        ] if isinstance(findings, list) else []
        if not blocking_findings:
            blocking_findings = ["Typesetting quality check failed."]
        repair_stage = str(report.get("repair_stage") or "typesetting")
        return {
            "blocking_findings": blocking_findings,
            "repair_stage": repair_stage,
        }

    def _score_paper_quality(self, workspace_root: Path) -> dict[str, object]:
        section_dir = workspace_root / "paper" / "sections"
        present = set()
        trace_lines = 0
        total_lines = 0
        if section_dir.exists():
            for section in section_dir.glob("*.tex"):
                text = section.read_text(encoding="utf-8")
                if text.strip():
                    present.add(section.name)
                lines = [line for line in text.splitlines() if line.strip()]
                total_lines += len(lines)
                trace_lines += sum(1 for line in lines if "claim_id=" in line)
        completeness = len(present & REQUIRED_PAPER_SECTIONS) / len(REQUIRED_PAPER_SECTIONS)
        trace_density = trace_lines / total_lines if total_lines else 0.0
        status = "pass" if completeness >= 0.85 and trace_density > 0 else "fail"
        return {
            "section_completeness": round(completeness, 3),
            "claim_trace_density": round(trace_density, 3),
            "status": status,
            "missing_sections": sorted(REQUIRED_PAPER_SECTIONS - present),
        }

    def _write_source_audit_report(self, workspace_root: Path, unbound_sources: list[str]) -> None:
        sources = read_json(workspace_root / "data" / "source_registry.json", [])
        lineage = read_json(workspace_root / "data" / "data_lineage.json", [])
        lines = [
            "# Source Audit Report",
            "",
            "## Summary",
            f"- Registered sources: {len(sources)}",
            f"- Data lineage records: {len(lineage)}",
            "",
        ]
        if unbound_sources:
            lines.extend(
                [
                    "## Unbound external data sources",
                    "",
                    *[f"- `{source_id}`" for source_id in unbound_sources],
                    "",
                ]
            )
        else:
            lines.extend(["## Unbound external data sources", "", "- None.", ""])
        (workspace_root / "review" / "source_audit_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    def _missing_references(self, workspace_root: Path) -> list[str]:
        reference_audit = workspace_root / "review" / "reference_audit_report.md"
        if reference_audit.exists():
            text = reference_audit.read_text(encoding="utf-8")
            if "Missing references: 0" in text:
                return []

        references = workspace_root / "paper" / "references.bib"
        references_text = references.read_text(encoding="utf-8") if references.exists() else ""
        used_source_ids = self._used_source_ids(workspace_root)
        return sorted(source_id for source_id in used_source_ids if source_id not in references_text)

    def _used_source_ids(self, workspace_root: Path) -> set[str]:
        used: set[str] = set()
        for item in read_json(workspace_root / "data" / "data_lineage.json", []):
            if isinstance(item, dict) and item.get("source_id"):
                source_id = str(item["source_id"])
                if source_id not in PLACEHOLDER_SOURCE_IDS:
                    used.add(source_id)
        for item in read_json(workspace_root / "figures" / "figure_registry.json", []):
            if isinstance(item, dict):
                used.update(
                    str(source_id)
                    for source_id in item.get("source_ids", [])
                    if source_id and str(source_id) not in PLACEHOLDER_SOURCE_IDS
                )
        section_dir = workspace_root / "paper" / "sections"
        if section_dir.exists():
            for section in section_dir.glob("*.tex"):
                used.update(
                    source_id
                    for source_id in SOURCE_ID_PATTERN.findall(section.read_text(encoding="utf-8"))
                    if source_id not in PLACEHOLDER_SOURCE_IDS
                )
        return used

    def _unresolved_critical_claims(self, workspace_root: Path) -> list[str]:
        rows = read_json(workspace_root / "paper" / "claim_plan.json", [])
        if not isinstance(rows, list):
            return []
        unresolved = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = PaperClaimPlanItem.model_validate(row)
            if item.priority == "critical" and item.status == "unresolved":
                unresolved.append(item.claim_id)
        return unresolved

    def _paper_binding_failure_reason(self, workspace_root: Path) -> tuple[list[str], bool]:
        bindings = read_json(workspace_root / "review" / "paper_evidence_bindings.json", [])
        if not isinstance(bindings, list):
            return [], False
        missing = []
        has_omitted_plan = False
        for binding in bindings:
            if isinstance(binding, dict) and binding.get("status") == "fail":
                missing.append(str(binding.get("section", "unknown_section")))
                missing_bindings = binding.get("missing_bindings", [])
                if isinstance(missing_bindings, list) and any(
                    "Omitted planned claims:" in str(item) for item in missing_bindings
                ):
                    has_omitted_plan = True
        return missing, has_omitted_plan

    def _fallback_review(self, blocking: list[str], language: str = "en") -> str:
        """Deterministic fallback review report in the paper language (zh or en)."""
        idx = 1 if language == "zh" else 0

        def s(key: str) -> str:
            return _REVIEW_STRINGS[key][idx]

        lines = [
            s("h1"),
            "",
            s("h2_score"),
            s("status_pass") if not blocking else s("status_blocked"),
            "",
            s("h2_strengths"),
            "- " + s("strength_workflow"),
            "",
            s("h2_risks"),
            *(f"- {issue}" for issue in blocking),
            "" if blocking else "- " + s("none"),
            "",
            s("h2_revisions"),
            "- " + s("revision_review"),
            "",
            s("h2_award"),
            "- " + s("award_modeling"),
            "",
            s("h2_suggestions"),
            "- " + s("suggestion_figures"),
            "",
        ]
        return "\n".join(lines)

    def _generate_review(self, blocking: list[str], language: str = "en") -> str | None:
        if self.llm_provider is None:
            return None
        idx = 1 if language == "zh" else 0

        def s(key: str) -> str:
            return _REVIEW_STRINGS[key][idx]

        h1 = s("required_h1")
        h2_score = s("required_h2_score")
        h2_risks = s("required_h2_risks")
        h2_suggestions = s("required_h2_suggestions")

        if language == "zh":
            sys_prompt = "你是严格的MCM/ICM赛前评审员。"
            task_line = "撰写简洁的赛前评审报告。"
            heading_line = (
                f"必须包含以下标题: {h1}, {h2_score}, {h2_risks}, {h2_suggestions}."
            )
        else:
            sys_prompt = "You are a strict MCM/ICM pre-submission reviewer."
            task_line = "Write a concise pre-submission review."
            heading_line = (
                f"Required headings: {h1}, {h2_score}, {h2_risks}, {h2_suggestions}."
            )

        prompt = "\n".join(
            [
                "# Reviewer",
                "",
                task_line,
                heading_line,
                "",
                "Blocking findings:",
                *(f"- {issue}" for issue in blocking),
            ]
        )
        result = self.llm_provider.generate(sys_prompt, prompt)
        content = result.content.strip()
        required = [h1, h2_score, h2_risks, h2_suggestions]
        if all(heading in content for heading in required):
            return content + "\n"
        return None
