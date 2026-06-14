from __future__ import annotations

import re
from pathlib import Path

from mcm_agent.utils.json_io import read_json, write_json


CLAIM_PATTERN = re.compile(r"claim_id=([A-Za-z0-9_-]+)")
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
        claim_bindings = self._claim_bindings_for_text(
            text,
            evidence_ids,
            figure_ids,
            source_ids,
        )
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
        for claim_binding in claim_bindings:
            if claim_binding.get("status") == "fail":
                missing.append(
                    "Claim-level binding failed: "
                    + str(claim_binding.get("claim_id", "unknown_claim"))
                )
        return {
            "section": str(section.relative_to(workspace_root)),
            "evidence_ids": found_evidence,
            "figure_ids": found_figures,
            "source_ids": found_sources,
            "claim_bindings": claim_bindings,
            "missing_bindings": missing,
            "status": "fail" if missing else "pass",
        }

    def _claim_bindings_for_text(
        self,
        text: str,
        evidence_ids: set[str],
        figure_ids: set[str],
        source_ids: set[str],
    ) -> list[dict[str, object]]:
        bindings = []
        for line in text.splitlines():
            claim_match = CLAIM_PATTERN.search(line)
            if claim_match is None:
                continue
            found_evidence = self._valid_ids(EVIDENCE_PATTERN.findall(line))
            found_figures = self._valid_ids(FIGURE_PATTERN.findall(line))
            found_sources = self._valid_ids(SOURCE_PATTERN.findall(line))
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
            known_evidence = [item for item in found_evidence if item in evidence_ids]
            known_figures = [item for item in found_figures if item in figure_ids]
            known_sources = [item for item in found_sources if item in source_ids]
            if not (known_evidence or known_figures or known_sources):
                missing.append("Claim has no evidence, figure, or source binding.")
            bindings.append(
                {
                    "claim_id": claim_match.group(1),
                    "evidence_ids": found_evidence,
                    "figure_ids": found_figures,
                    "source_ids": found_sources,
                    "missing_bindings": missing,
                    "status": "fail" if missing else "pass",
                }
            )
        return bindings

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
            claim_bindings = binding.get("claim_bindings", [])
            if isinstance(claim_bindings, list) and claim_bindings:
                lines.append("  - claim_bindings: " + str(len(claim_bindings)))
        claim_rows = [
            (binding, claim_binding)
            for binding in bindings
            for claim_binding in binding.get("claim_bindings", [])
            if isinstance(claim_binding, dict)
        ]
        if claim_rows:
            lines.extend(["", "## Claim Bindings"])
            for binding, claim_binding in claim_rows:
                lines.extend(
                    [
                        f"- `{claim_binding['claim_id']}`: {claim_binding['status']}",
                        f"  - section: `{binding['section']}`",
                        f"  - evidence_ids: {', '.join(claim_binding['evidence_ids']) or 'none'}",
                        f"  - figure_ids: {', '.join(claim_binding['figure_ids']) or 'none'}",
                        f"  - source_ids: {', '.join(claim_binding['source_ids']) or 'none'}",
                    ]
                )
                missing = claim_binding.get("missing_bindings", [])
                if isinstance(missing, list) and missing:
                    lines.append("  - missing: " + "; ".join(str(item) for item in missing))
        (workspace_root / "review" / "paper_evidence_report.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
