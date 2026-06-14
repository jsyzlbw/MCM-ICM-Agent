from __future__ import annotations

import re
from pathlib import Path

from mcm_agent.utils.json_io import read_json, write_json


EVIDENCE_PATTERN = re.compile(r"evidence_id=([A-Za-z0-9_-]+)")
FIGURE_PATTERN = re.compile(r"figure_id=([A-Za-z0-9_-]+)")
SOURCE_PATTERN = re.compile(r"source_id=([A-Za-z0-9_-]+)")
CLAIM_SECTIONS = {"conclusion.tex", "model.tex", "results.tex", "sensitivity.tex"}
PLACEHOLDER_IDS = {"missing", "none", "unknown"}


class PaperEvidenceBindingAgent:
    def run(self, workspace_root: Path) -> None:
        evidence_ids = self._registry_ids(
            workspace_root / "results" / "evidence_registry.json",
            "evidence_id",
        )
        figure_ids = self._registry_ids(
            workspace_root / "figures" / "figure_registry.json",
            "figure_id",
        )
        source_ids = self._registry_ids(
            workspace_root / "data" / "source_registry.json",
            "source_id",
        )
        bindings = []
        section_dir = workspace_root / "paper" / "sections"
        if section_dir.exists():
            for section in sorted(section_dir.glob("*.tex")):
                bindings.append(
                    self._binding_for_section(
                        workspace_root,
                        section,
                        evidence_ids,
                        figure_ids,
                        source_ids,
                    )
                )
        write_json(workspace_root / "review" / "paper_evidence_bindings.json", bindings)
        self._write_report(workspace_root, bindings)

    def _binding_for_section(
        self,
        workspace_root: Path,
        section: Path,
        evidence_ids: set[str],
        figure_ids: set[str],
        source_ids: set[str],
    ) -> dict[str, object]:
        text = section.read_text(encoding="utf-8")
        found_evidence = self._valid_ids(EVIDENCE_PATTERN.findall(text))
        found_figures = self._valid_ids(FIGURE_PATTERN.findall(text))
        found_sources = self._valid_ids(SOURCE_PATTERN.findall(text))
        missing = []
        unknown_evidence = sorted(set(found_evidence) - evidence_ids)
        unknown_figures = sorted(set(found_figures) - figure_ids)
        unknown_sources = sorted(set(found_sources) - source_ids)
        if unknown_evidence:
            missing.append("Unknown evidence ids: " + ", ".join(unknown_evidence))
        if unknown_figures:
            missing.append("Unknown figure ids: " + ", ".join(unknown_figures))
        if unknown_sources:
            missing.append("Unknown source ids: " + ", ".join(unknown_sources))
        if section.name in CLAIM_SECTIONS and not (found_evidence or found_figures or found_sources):
            missing.append("Claim-bearing section has no evidence, figure, or source binding.")
        return {
            "section": str(section.relative_to(workspace_root)),
            "evidence_ids": found_evidence,
            "figure_ids": found_figures,
            "source_ids": found_sources,
            "missing_bindings": missing,
            "status": "fail" if missing else "pass",
        }

    def _registry_ids(self, path: Path, key: str) -> set[str]:
        rows = read_json(path, [])
        if not isinstance(rows, list):
            return set()
        return {
            str(row[key])
            for row in rows
            if isinstance(row, dict)
            and row.get(key)
            and str(row[key]) not in PLACEHOLDER_IDS
        }

    def _valid_ids(self, values: list[str]) -> list[str]:
        deduped = []
        seen = set()
        for value in values:
            if value in PLACEHOLDER_IDS or value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def _write_report(self, workspace_root: Path, bindings: list[dict[str, object]]) -> None:
        failing = [binding for binding in bindings if binding.get("status") == "fail"]
        lines = [
            "# Paper Evidence Report",
            "",
            f"Missing bindings: {len(failing)}",
            "",
            "## Section Bindings",
        ]
        for binding in bindings:
            lines.extend(
                [
                    f"- `{binding['section']}`: {binding['status']}",
                    f"  - evidence_ids: {', '.join(binding['evidence_ids']) or 'none'}",
                    f"  - figure_ids: {', '.join(binding['figure_ids']) or 'none'}",
                    f"  - source_ids: {', '.join(binding['source_ids']) or 'none'}",
                ]
            )
            missing = binding.get("missing_bindings", [])
            if isinstance(missing, list) and missing:
                lines.append("  - missing: " + "; ".join(str(item) for item in missing))
        (workspace_root / "review" / "paper_evidence_report.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
