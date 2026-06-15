from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json, write_json


class TypesettingIssue(BaseModel):
    issue_type: str
    severity: str
    message: str
    repair_stage: str
    evidence: str = ""


class TypesettingQAReport(BaseModel):
    status: str
    issue_types: list[str] = Field(default_factory=list)
    blocking_findings: list[str] = Field(default_factory=list)
    repair_stage: str | None = None
    issues: list[TypesettingIssue] = Field(default_factory=list)
    page_count: int | None = None


class TypesettingQAAgent:
    def run(self, workspace_root: Path, *, max_pages: int = 25) -> TypesettingQAReport:
        paper_dir = workspace_root / "paper"
        tex_path = paper_dir / "main.tex"
        pdf_path = paper_dir / "main.pdf"
        log_path = paper_dir / "compile_log.txt"
        tex = tex_path.read_text(encoding="utf-8") if tex_path.exists() else ""
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

        issues: list[TypesettingIssue] = []
        issues.extend(self._compile_errors(log))
        issues.extend(self._missing_pdf_issues(workspace_root, pdf_path, log))
        issues.extend(self._table_issues(tex, log))
        issues.extend(self._equation_issues(tex, log))
        issues.extend(self._figure_issues(tex, paper_dir, log))
        page_count = self._page_count(workspace_root, tex)
        if page_count is not None and page_count > max_pages:
            issues.append(
                TypesettingIssue(
                    issue_type="page_limit_risk",
                    severity="blocking",
                    message=f"Paper page count {page_count} exceeds limit {max_pages}.",
                    repair_stage="typesetting",
                    evidence=f"page_count={page_count}",
                )
            )

        blocking = [issue.message for issue in issues if issue.severity == "blocking"]
        repair_stage = self._repair_stage(issues)
        report = TypesettingQAReport(
            status="fail" if blocking else "pass",
            issue_types=sorted({issue.issue_type for issue in issues}),
            blocking_findings=blocking,
            repair_stage=repair_stage,
            issues=issues,
            page_count=page_count,
        )
        self._write_reports(workspace_root, report)
        return report

    def _compile_errors(self, log: str) -> list[TypesettingIssue]:
        issues: list[TypesettingIssue] = []
        for line in log.splitlines():
            stripped = line.strip()
            if (
                stripped.startswith("! ")
                or "LaTeX Error" in stripped
                or "Emergency stop" in stripped
            ):
                issues.append(
                    TypesettingIssue(
                        issue_type="compile_error",
                        severity="blocking",
                        message=f"LaTeX compile error: {stripped}",
                        repair_stage="typesetting",
                        evidence=stripped,
                    )
                )
                break
        return issues

    def _missing_pdf_issues(
        self,
        workspace_root: Path,
        pdf_path: Path,
        log: str,
    ) -> list[TypesettingIssue]:
        if pdf_path.exists():
            return []
        report_text = ""
        report_path = workspace_root / "review" / "typesetting_report.md"
        if report_path.exists():
            report_text = report_path.read_text(encoding="utf-8")
        if log or "Success: False" in report_text:
            return [
                TypesettingIssue(
                    issue_type="missing_pdf",
                    severity="blocking",
                    message="Compiled PDF is missing.",
                    repair_stage="typesetting",
                    evidence=str(pdf_path),
                )
            ]
        return []

    def _table_issues(self, tex: str, log: str) -> list[TypesettingIssue]:
        issues: list[TypesettingIssue] = []
        for spec in re.findall(r"\\begin\{tabular\}\{([^}]*)\}", tex):
            columns = sum(1 for char in spec if char in {"l", "c", "r", "p", "m", "b", "X"})
            if columns >= 9:
                issues.append(
                    TypesettingIssue(
                        issue_type="table_overflow_risk",
                        severity="blocking",
                        message=f"Wide table has {columns} declared columns.",
                        repair_stage="typesetting",
                        evidence=spec,
                    )
                )
                break
        if "Overfull \\hbox" in log and not any(
            issue.issue_type == "table_overflow_risk" for issue in issues
        ):
            issues.append(
                TypesettingIssue(
                    issue_type="table_overflow_risk",
                    severity="warning",
                    message="Compile log reports an overfull horizontal box.",
                    repair_stage="typesetting",
                    evidence="Overfull \\hbox",
                )
            )
        return issues

    def _equation_issues(self, tex: str, log: str) -> list[TypesettingIssue]:
        issues: list[TypesettingIssue] = []
        for block in re.findall(r"\\begin\{equation\}(.*?)\\end\{equation\}", tex, re.S):
            long_lines = [line.strip() for line in block.splitlines() if len(line.strip()) > 100]
            if long_lines:
                issues.append(
                    TypesettingIssue(
                        issue_type="equation_overflow_risk",
                        severity="blocking",
                        message="Long display equation may overflow the page width.",
                        repair_stage="paper_writer",
                        evidence=long_lines[0][:160],
                    )
                )
                break
        if "Overfull \\hbox" in log and re.search(r"\\begin\{equation\}|\\\[", tex):
            if not any(issue.issue_type == "equation_overflow_risk" for issue in issues):
                issues.append(
                    TypesettingIssue(
                        issue_type="equation_overflow_risk",
                        severity="warning",
                        message="Compile log reports overfull boxes near display math.",
                        repair_stage="paper_writer",
                        evidence="Overfull \\hbox",
                    )
                )
        return issues

    def _figure_issues(self, tex: str, paper_dir: Path, log: str) -> list[TypesettingIssue]:
        issues: list[TypesettingIssue] = []
        if tex.count("[H]") > 8:
            issues.append(
                TypesettingIssue(
                    issue_type="figure_placement_risk",
                    severity="warning",
                    message="Many figures use strict [H] placement.",
                    repair_stage="typesetting",
                    evidence=f"[H] count={tex.count('[H]')}",
                )
            )
        for figure_path in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", tex):
            candidate = (paper_dir / figure_path).resolve()
            if not candidate.exists():
                issues.append(
                    TypesettingIssue(
                        issue_type="figure_file_missing",
                        severity="blocking",
                        message=f"Included figure file is missing: {figure_path}",
                        repair_stage="visualization",
                        evidence=figure_path,
                    )
                )
                break
        if "Float too large" in log:
            issues.append(
                TypesettingIssue(
                    issue_type="figure_placement_risk",
                    severity="blocking",
                    message="Compile log reports a float that is too large.",
                    repair_stage="visualization",
                    evidence="Float too large",
                )
            )
        return issues

    def _page_count(self, workspace_root: Path, tex: str) -> int | None:
        payload = read_json(workspace_root / "review" / "typesetting_report.json", {})
        if isinstance(payload, dict):
            page_count = payload.get("page_count")
            if isinstance(page_count, int):
                return page_count
        marker_count = tex.count("%%PAGE")
        return marker_count or None

    def _repair_stage(self, issues: list[TypesettingIssue]) -> str | None:
        blocking = [issue for issue in issues if issue.severity == "blocking"]
        if not blocking:
            return None
        if any(issue.repair_stage == "visualization" for issue in blocking):
            return "visualization"
        if any(issue.repair_stage == "paper_writer" for issue in blocking):
            return "paper_writer"
        return "typesetting"

    def _write_reports(self, workspace_root: Path, report: TypesettingQAReport) -> None:
        review_dir = workspace_root / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "typesetting_quality.json", report.model_dump())
        lines = [
            "# Typesetting Quality Report",
            "",
            f"- Status: {report.status}",
            f"- Repair stage: {report.repair_stage or 'none'}",
            f"- Page count: {report.page_count if report.page_count is not None else 'unknown'}",
            "",
            "## Findings",
            "",
        ]
        if report.issues:
            lines.extend(
                f"- [{issue.severity}] {issue.issue_type}: {issue.message} Evidence: {issue.evidence}"
                for issue in report.issues
            )
        else:
            lines.append("- No blocking typesetting issues detected.")
        lines.append("")
        (review_dir / "typesetting_quality_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )
