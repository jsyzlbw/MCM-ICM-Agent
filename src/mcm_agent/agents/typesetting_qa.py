from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json, write_json

# ---------------------------------------------------------------------------
# Off-language lint helpers
# ---------------------------------------------------------------------------

# CJK Unified Ideographs (basic block) – a run of these in an en paper is a violation.
_CJK_CHAR = re.compile(r'[一-鿿]')

# Strip LaTeX commands, math, citations, and file paths before scanning for
# prose runs so we don't flag \\textbf{}, $x+y$, \\cite{...}, etc.
_STRIP_LATEX = re.compile(
    r"""
    \\[a-zA-Z]+\*?     # \command or \command*
    (?:\[[^\]]*\])?    # optional [opt]
    (?:\{[^}]*\})*     # zero or more {arg}
    | \$[^$]*\$        # inline math $...$
    | \$\$[^$]*\$\$    # display math $$...$$
    | %[^\n]*          # % comments
    | \[[^\]]*\]       # [something]
    | \{[^}]*\}        # {something} not caught above
    """,
    re.VERBOSE,
)

# A "long" Latin-ASCII word run for zh-paper lint: ≥4 consecutive words that
# are all ASCII alphabetic (length ≥ 3 each) separated only by spaces.
# This catches full English sentences but ignores single acronyms like SVM/AUC.
_LONG_ASCII_WORD_RUN = re.compile(
    r'\b(?:[A-Za-z]{3,}\s+){3,}[A-Za-z]{3,}\b'
)

# CJK sentence: ≥8 consecutive CJK characters (catches zh sentences in en papers).
_LONG_CJK_RUN = re.compile(r'[一-鿿]{8,}')


def _strip_latex_noise(tex: str) -> str:
    """Remove LaTeX markup so the scanner only sees prose words."""
    return _STRIP_LATEX.sub(' ', tex)


def _off_language_evidence(tex: str, language: str) -> str:
    """Return the first offending snippet if the tex body violates language purity,
    or an empty string if clean.

    Conservative heuristic:
    - zh paper: flag a run of ≥4 consecutive long ASCII words that are prose
      (contain at least one lowercase letter), NOT all-caps acronyms like SVM/AUC.
    - en paper: flag ≥8 consecutive CJK characters (sentence-level leakage).
    """
    prose = _strip_latex_noise(tex)
    if language == "zh":
        # Find all potential English word runs and filter by prose-ness.
        # Only count tokens with at least one lowercase letter as prose.
        for m in _LONG_ASCII_WORD_RUN.finditer(prose):
            candidate = m.group(0)
            # Split into tokens and count those with lowercase letters
            tokens = candidate.split()
            prose_count = sum(1 for token in tokens if any(c.islower() for c in token))
            # If ≥4 tokens contain lowercase (i.e., are real prose, not acronyms),
            # then this is a prose run worth flagging.
            if prose_count >= 4:
                return candidate[:120]
        return ""
    else:
        m = _LONG_CJK_RUN.search(prose)
        return m.group(0)[:120] if m else ""


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
        from mcm_agent.agents.discussion import confirmed_language  # local import avoids cycles

        paper_dir = workspace_root / "paper"
        tex_path = paper_dir / "main.tex"
        pdf_path = paper_dir / "main.pdf"
        log_path = paper_dir / "compile_log.txt"
        tex = tex_path.read_text(encoding="utf-8") if tex_path.exists() else ""
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        language = confirmed_language(workspace_root)

        issues: list[TypesettingIssue] = []
        issues.extend(self._compile_errors(log))
        issues.extend(self._missing_pdf_issues(workspace_root, pdf_path, log))
        issues.extend(self._table_issues(tex, log))
        issues.extend(self._equation_issues(tex, log))
        issues.extend(self._figure_issues(tex, paper_dir, log))
        issues.extend(self._off_language_issues(tex, language))
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
        if "latexmk not installed" in log.lower() or "latexmk not installed" in report_text.lower():
            return [
                TypesettingIssue(
                    issue_type="latex_tool_unavailable",
                    severity="warning",
                    message="LaTeX compiler is unavailable; PDF layout QA was skipped.",
                    repair_stage="typesetting",
                    evidence="latexmk not installed",
                )
            ]
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

    def _off_language_issues(self, tex: str, language: str) -> list[TypesettingIssue]:
        """Detect sentence-level off-language content in the .tex body.

        Conservative approach:
        - zh paper: flag runs of ≥4 consecutive long ASCII words in prose (catches
          full English paragraphs, not single acronyms like SVM/AUC).
        - en paper: flag runs of ≥8 consecutive CJK characters in prose.
        LaTeX commands, math, citations, and comments are stripped first.
        """
        evidence = _off_language_evidence(tex, language)
        if not evidence:
            return []
        off_lang = "English" if language == "zh" else "Chinese"
        msg = (
            f"Off-language content detected ({off_lang} prose in {language} paper). "
            "Check section bodies for language leakage."
        )
        return [
            TypesettingIssue(
                issue_type="off_language_prose",
                severity="blocking",
                message=msg,
                repair_stage="paper_writer",
                evidence=evidence,
            )
        ]

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
        repair_summary = self._repair_summary_lines(review_dir / "typesetting_repair.json")
        if repair_summary:
            lines.extend(["", "## Repair Summary", "", *repair_summary])
        lines.append("")
        (review_dir / "typesetting_quality_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    def _repair_summary_lines(self, repair_path: Path) -> list[str]:
        payload = read_json(repair_path, {})
        if not isinstance(payload, dict) or not payload:
            return []
        lines = [f"- Repair status: {payload.get('status', 'unknown')}"]
        actions = payload.get("actions", [])
        if not isinstance(actions, list) or not actions:
            lines.append("- Repair actions: none.")
            return lines
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_type = action.get("action_type", "unknown")
            message = action.get("message", "")
            changed = action.get("changed", False)
            lines.append(f"- [{action_type}] {message} changed={changed}")
        return lines
