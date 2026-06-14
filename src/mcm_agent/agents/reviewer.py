from __future__ import annotations

import re
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.core.lineage import find_unbound_external_data
from mcm_agent.providers.base import TextGenerationProvider
from mcm_agent.utils.json_io import read_json


SOURCE_ID_PATTERN = re.compile(r"source_id=([A-Za-z0-9_-]+)")
PLACEHOLDER_SOURCE_IDS = {"missing", "none", "unknown"}


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
        missing_paper_bindings = self._missing_paper_bindings(workspace_root)
        if missing_paper_bindings:
            blocking.append(
                "Paper claims are missing evidence bindings: "
                + ", ".join(f"`{section}`" for section in missing_paper_bindings)
                + "."
            )
        self._write_source_audit_report(workspace_root, unbound_sources)

        reviewer_report = self._generate_review(blocking) or self._fallback_review(blocking)
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
        elif missing_paper_bindings:
            failure_reason = "bad_writing"
            repair_stage = "paper_writer"
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

    def _missing_paper_bindings(self, workspace_root: Path) -> list[str]:
        bindings = read_json(workspace_root / "review" / "paper_evidence_bindings.json", [])
        if not isinstance(bindings, list):
            return []
        missing = []
        for binding in bindings:
            if isinstance(binding, dict) and binding.get("status") == "fail":
                missing.append(str(binding.get("section", "unknown_section")))
        return missing

    def _fallback_review(self, blocking: list[str]) -> str:
        return "\n".join(
            [
                "# 自动评审报告",
                "",
                "## 总体评分",
                "Pass with comments." if not blocking else "Blocked.",
                "",
                "## 主要优点",
                "- The workflow records evidence, figures, and review artifacts.",
                "",
                "## 高风险问题",
                *(f"- {issue}" for issue in blocking),
                "" if blocking else "- None.",
                "",
                "## 需要修改的问题",
                "- Review all generated sections before submission.",
                "",
                "## 可能影响奖项的问题",
                "- Missing deep domain-specific modeling may affect competitiveness.",
                "",
                "## 修改建议",
                "- Improve model-specific explanation and figure captions.",
                "",
            ]
        )

    def _generate_review(self, blocking: list[str]) -> str | None:
        if self.llm_provider is None:
            return None
        prompt = "\n".join(
            [
                "# Reviewer",
                "",
                "Write a concise pre-submission review.",
                "Required headings: # 自动评审报告, ## 总体评分, ## 高风险问题, ## 修改建议.",
                "",
                "Blocking findings:",
                *(f"- {issue}" for issue in blocking),
            ]
        )
        result = self.llm_provider.generate("You are a strict MCM/ICM pre-submission reviewer.", prompt)
        content = result.content.strip()
        required = ["# 自动评审报告", "## 总体评分", "## 高风险问题", "## 修改建议"]
        if all(heading in content for heading in required):
            return content + "\n"
        return None
