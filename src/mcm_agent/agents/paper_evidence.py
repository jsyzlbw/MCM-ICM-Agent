from __future__ import annotations

import re
from pathlib import Path

from mcm_agent.core.models import PaperClaimPlanItem
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
        claim_plan = self._read_claim_plan(workspace_root)
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
                        claim_plan,
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
        claim_plan: dict[str, PaperClaimPlanItem],
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
        missing.extend(
            self._planned_coverage_missing(
                claim_plan,
                section,
                workspace_root,
                claim_bindings,
            )
        )
        for claim_binding in claim_bindings:
            missing.extend(self._claim_plan_subset_missing(claim_plan, claim_binding))
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

    def _read_claim_plan(self, workspace_root: Path) -> dict[str, PaperClaimPlanItem]:
        rows = read_json(workspace_root / "paper" / "claim_plan.json", [])
        if not isinstance(rows, list):
            return {}
        return {
            item.claim_id: item
            for item in (
                PaperClaimPlanItem.model_validate(row)
                for row in rows
                if isinstance(row, dict)
            )
        }

    def _planned_claims_for_section(
        self,
        claim_plan: dict[str, PaperClaimPlanItem],
        section: Path,
        workspace_root: Path,
    ) -> list[PaperClaimPlanItem]:
        section_path = str(section.relative_to(workspace_root))
        return [
            item
            for item in claim_plan.values()
            if item.section == section_path
            and item.status != "unresolved"
            and item.priority in {"critical", "major"}
        ]

    def _planned_coverage_missing(
        self,
        claim_plan: dict[str, PaperClaimPlanItem],
        section: Path,
        workspace_root: Path,
        claim_bindings: list[dict[str, object]],
    ) -> list[str]:
        written_claim_ids = {
            str(binding["claim_id"])
            for binding in claim_bindings
            if isinstance(binding, dict) and binding.get("claim_id")
        }
        planned = self._planned_claims_for_section(claim_plan, section, workspace_root)
        omitted = [item.claim_id for item in planned if item.claim_id not in written_claim_ids]
        return ["Omitted planned claims: " + ", ".join(omitted)] if omitted else []

    def _claim_plan_subset_missing(
        self,
        claim_plan: dict[str, PaperClaimPlanItem],
        claim_binding: dict[str, object],
    ) -> list[str]:
        claim_id = str(claim_binding.get("claim_id", ""))
        planned = claim_plan.get(claim_id)
        if planned is None or planned.status == "unresolved":
            return []
        missing = []
        for key, planned_values, label in (
            ("evidence_ids", planned.evidence_ids, "Evidence"),
            ("figure_ids", planned.figure_ids, "Figure"),
            ("source_ids", planned.source_ids, "Source"),
        ):
            found_values = [str(value) for value in claim_binding.get(key, [])]
            outside = sorted(set(found_values) - set(planned_values))
            if outside:
                missing.append(f"{label} ids outside claim plan: " + ", ".join(outside))
        return missing

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
