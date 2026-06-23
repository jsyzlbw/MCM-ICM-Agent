from __future__ import annotations

from pathlib import Path
from typing import Any

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.utils.json_io import read_json


class FigureQualityAgent:
    def run(self, workspace_root: Path) -> None:
        plan_items = read_json(workspace_root / "figures" / "figure_plan.json", [])
        registry_items = read_json(workspace_root / "figures" / "figure_registry.json", [])
        registry_by_id = {
            str(item.get("figure_id")): item
            for item in registry_items
            if isinstance(item, dict) and item.get("figure_id")
        }

        issues: list[str] = []
        for item in plan_items:
            if not isinstance(item, dict):
                issues.append("Figure plan contains a non-object item.")
                continue
            issues.extend(self._plan_issues(workspace_root, item))
            record = registry_by_id.get(str(item.get("figure_id")))
            if record is None:
                issues.append(f"Figure `{item.get('figure_id', 'unknown')}` is missing from registry.")
                continue
            issues.extend(self._registry_issues(workspace_root, item, record))

        if not plan_items:
            issues.append("Figure plan is empty.")

        issues.extend(self._embedding_issues(workspace_root, registry_items))

        self._write_report(workspace_root, issues)
        record_gate_decision(
            workspace_root,
            "figure_gate.json",
            GateDecision(
                gate_id="figure_quality_gate",
                status="fail" if issues else "pass",
                failure_reason="visual_or_vector_issue" if issues else None,
                repair_stage="figure_planning" if issues else None,
                blocking_findings=issues,
            ),
        )
        Coordinator(workspace_root).emit(
            "figures.review.failed" if issues else "figures.review.passed",
            source="FigureQualityAgent",
        )

    def _plan_issues(self, workspace_root: Path, item: dict[str, Any]) -> list[str]:
        figure_id = str(item.get("figure_id", "unknown"))
        issues: list[str] = []
        if not str(item.get("caption_intent", "")).strip():
            issues.append(f"Figure `{figure_id}` is missing caption intent.")
        if not str(item.get("target_section", "")).strip():
            issues.append(f"Figure `{figure_id}` is missing target paper section.")
        if item.get("figure_type") == "data_plot":
            source_data = self._string_list(item.get("source_data"))
            if not source_data:
                issues.append(f"Data figure `{figure_id}` has no source data.")
            for source_path in source_data:
                if not (workspace_root / source_path).exists():
                    issues.append(f"Data figure `{figure_id}` source data does not exist: `{source_path}`.")
            if not self._string_list(item.get("evidence_ids")):
                issues.append(f"Data figure `{figure_id}` is missing evidence_ids.")
        return issues

    def _registry_issues(
        self,
        workspace_root: Path,
        plan_item: dict[str, Any],
        record: dict[str, Any],
    ) -> list[str]:
        figure_id = str(plan_item.get("figure_id", record.get("figure_id", "unknown")))
        issues: list[str] = []
        source_file = str(record.get("source_file", "")).strip()
        if not source_file:
            issues.append(f"Figure `{figure_id}` has no generation script/source file.")
        elif not (workspace_root / source_file).exists():
            issues.append(f"Figure `{figure_id}` generation source does not exist: `{source_file}`.")

        outputs = self._string_list(record.get("outputs"))
        if not outputs:
            issues.append(f"Figure `{figure_id}` has no registered outputs.")
        for output in outputs:
            if not (workspace_root / output).exists():
                issues.append(f"Figure `{figure_id}` output does not exist: `{output}`.")

        used_in = self._string_list(record.get("used_in"))
        if not used_in:
            issues.append(f"Figure `{figure_id}` is missing target paper location.")

        if plan_item.get("figure_type") == "data_plot":
            has_vector = any(output.endswith((".pdf", ".svg")) for output in outputs)
            if not has_vector:
                issues.append(f"Data figure `{figure_id}` has no PDF/SVG output.")
        if plan_item.get("figure_type") == "concept_diagram":
            if source_file and not source_file.endswith(".mmd"):
                issues.append(f"Concept diagram `{figure_id}` source is not Mermaid `.mmd`.")
            has_vector = any(output.endswith((".eps", ".pdf", ".svg")) for output in outputs)
            if not has_vector:
                issues.append(f"Concept diagram `{figure_id}` has no SVG/PDF output.")
        return issues

    def _write_report(self, workspace_root: Path, issues: list[str]) -> None:
        lines = [
            "# Figure Quality Report",
            "",
            f"Blocking issues: {len(issues)}",
            "",
            "## Blocking Issues",
            *(f"- {issue}" for issue in issues),
            "" if issues else "- None.",
            "",
        ]
        (workspace_root / "review" / "figure_quality_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    def _embedding_issues(
        self, workspace_root: Path, registry_items: list[dict[str, Any]]
    ) -> list[str]:
        """Return a blocking finding for each registered figure that is NOT
        embedded (no \\includegraphics referencing its id) in any written .tex file."""
        if not registry_items:
            return []

        # Collect all .tex content from paper/sections/ and paper/main.tex.
        tex_content = ""
        sections_dir = workspace_root / "paper" / "sections"
        if sections_dir.exists():
            for tex_file in sections_dir.glob("*.tex"):
                tex_content += tex_file.read_text(encoding="utf-8")
        main_tex = workspace_root / "paper" / "main.tex"
        if main_tex.exists():
            tex_content += main_tex.read_text(encoding="utf-8")

        if not tex_content:
            # Paper not written yet — skip embedding check.
            return []

        issues: list[str] = []
        for record in registry_items:
            if not isinstance(record, dict):
                continue
            figure_id = str(record.get("figure_id", "")).strip()
            if not figure_id:
                continue
            if "\\includegraphics" not in tex_content:
                issues.append(
                    f"Figure `{figure_id}` is not embedded in the paper "
                    "(no \\includegraphics found in any written .tex file)."
                )
            elif figure_id not in tex_content:
                issues.append(
                    f"Figure `{figure_id}` is not embedded in the paper "
                    f"(\\includegraphics present but `{figure_id}` not referenced)."
                )
        return issues

    def _string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]
