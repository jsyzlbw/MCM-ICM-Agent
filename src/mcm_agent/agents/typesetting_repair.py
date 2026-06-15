from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import read_json, write_json


class TypesettingRepairAction(BaseModel):
    action_type: str
    message: str
    changed: bool


class TypesettingRepairReport(BaseModel):
    status: Literal["repaired", "no_action", "skipped"]
    actions: list[TypesettingRepairAction] = Field(default_factory=list)


class TypesettingRepairAgent:
    def run(self, workspace_root: Path) -> TypesettingRepairReport:
        quality = read_json(workspace_root / "review" / "typesetting_quality.json", {})
        tex_path = workspace_root / "paper" / "main.tex"
        tex = tex_path.read_text(encoding="utf-8") if tex_path.exists() else ""
        if not isinstance(quality, dict) or quality.get("status") != "fail":
            report = TypesettingRepairReport(status="skipped")
            self._write_repair_report(workspace_root, report)
            return report

        issue_types = {
            str(issue_type)
            for issue_type in quality.get("issue_types", [])
            if str(issue_type).strip()
        }
        actions: list[TypesettingRepairAction] = []
        updated = tex
        if "table_overflow_risk" in issue_types:
            updated, changed = self._wrap_wide_tables(updated)
            actions.append(
                TypesettingRepairAction(
                    action_type="wrap_wide_tables",
                    message="Wrapped wide tabular environments in resizebox.",
                    changed=changed,
                )
            )
        if issue_types.intersection({"figure_file_missing", "figure_placement_risk"}):
            updated, changed = self._scale_graphics(updated)
            actions.append(
                TypesettingRepairAction(
                    action_type="scale_graphics",
                    message="Added width limits to unscaled includegraphics calls.",
                    changed=changed,
                )
            )
        if "equation_overflow_risk" in issue_types:
            updated, changed = self._wrap_long_equations(updated)
            actions.append(
                TypesettingRepairAction(
                    action_type="wrap_long_equations",
                    message="Wrapped long equation bodies in split environments.",
                    changed=changed,
                )
            )

        changed_any = updated != tex
        if changed_any:
            tex_path.write_text(updated, encoding="utf-8")
        report = TypesettingRepairReport(
            status="repaired" if changed_any else "no_action",
            actions=actions,
        )
        self._write_repair_report(workspace_root, report)
        return report

    def _wrap_wide_tables(self, tex: str) -> tuple[str, bool]:
        pattern = re.compile(r"(?<!\\resizebox\{\\textwidth\}\{!\}\{%\n)(\\begin\{tabular\}\{[^}]*\}.*?\\end\{tabular\})", re.S)

        def replace(match: re.Match[str]) -> str:
            block = match.group(1)
            if "\\resizebox{\\textwidth}{!}{%" in block:
                return block
            return "\\resizebox{\\textwidth}{!}{%\n" + block + "\n}"

        updated = pattern.sub(replace, tex)
        return updated, updated != tex

    def _scale_graphics(self, tex: str) -> tuple[str, bool]:
        pattern = re.compile(r"\\includegraphics\{([^}]*)\}")
        updated = pattern.sub(r"\\includegraphics[width=0.9\\linewidth]{\1}", tex)
        return updated, updated != tex

    def _wrap_long_equations(self, tex: str) -> tuple[str, bool]:
        pattern = re.compile(r"\\begin\{equation\}(.*?)\\end\{equation\}", re.S)

        def replace(match: re.Match[str]) -> str:
            body = match.group(1)
            if re.search(r"\\begin\{(?:split|aligned|multline|gathered)\}", body):
                return match.group(0)
            if not any(len(line.strip()) > 100 for line in body.splitlines()):
                return match.group(0)
            wrapped = self._split_equation_body(body)
            return "\\begin{equation}\n\\begin{split}\n" + wrapped + "\n\\end{split}\n\\end{equation}"

        updated = pattern.sub(replace, tex)
        return updated, updated != tex

    def _split_equation_body(self, body: str) -> str:
        stripped = " ".join(line.strip() for line in body.splitlines() if line.strip())
        if len(stripped) <= 100 or " + " not in stripped:
            return stripped
        left, separator, right = stripped.partition("=")
        prefix = f"{left.strip()} {separator}".strip() if separator else ""
        terms = [term.strip() for term in right.split(" + ") if term.strip()] if separator else [
            term.strip() for term in stripped.split(" + ") if term.strip()
        ]
        lines: list[str] = []
        current = prefix
        for index, term in enumerate(terms):
            token = term if index == 0 and prefix else f"+ {term}"
            candidate = f"{current} {token}".strip()
            if current and len(candidate) > 88:
                lines.append(current + r" \\")
                current = f"& {token}"
            else:
                current = candidate
        if current:
            lines.append(current)
        return "\n".join(lines)

    def _write_repair_report(
        self,
        workspace_root: Path,
        report: TypesettingRepairReport,
    ) -> None:
        review_dir = workspace_root / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "typesetting_repair.json", report.model_dump())
        lines = [
            "# Typesetting Repair Report",
            "",
            f"- Status: {report.status}",
            "",
            "## Actions",
        ]
        if report.actions:
            lines.extend(
                f"- [{action.action_type}] {action.message} changed={action.changed}"
                for action in report.actions
            )
        else:
            lines.append("- None.")
        lines.append("")
        (review_dir / "typesetting_repair_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )
