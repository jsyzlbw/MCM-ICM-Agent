from __future__ import annotations

from pathlib import Path

from mcm_agent.core.coordinator import Coordinator


class ReviewerAgent:
    def run(self, workspace_root: Path) -> None:
        unresolved = (workspace_root / "unresolved_issues.md").read_text(encoding="utf-8")
        fact_report = workspace_root / "review" / "fact_regression_report.md"
        fact_text = fact_report.read_text(encoding="utf-8") if fact_report.exists() else ""
        blocking: list[str] = []
        if "[[UNRESOLVED:" in unresolved:
            blocking.append("Unresolved placeholders remain.")
        if "critical" in fact_text:
            blocking.append("Critical fact regression remains.")

        reviewer_report = "\n".join(
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
        Coordinator(workspace_root).emit(
            "paper.review.failed" if blocking else "paper.review.passed",
            source="ReviewerAgent",
        )
