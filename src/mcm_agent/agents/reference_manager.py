from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.citations import CitationContext, build_citation_context
from mcm_agent.core.models import CitationCandidate
from mcm_agent.utils.json_io import read_json


SOURCE_ID_PATTERN = re.compile(r"source_id=([A-Za-z0-9_-]+)")
PLACEHOLDER_SOURCE_IDS = {"missing", "none", "unknown"}


class ReferenceManager:
    def run(self, workspace_root: Path) -> None:
        registered_source_ids = self._registered_source_ids(workspace_root)
        candidates = self._registered_candidates(workspace_root, registered_source_ids)
        citation_context = build_citation_context(workspace_root)
        used_source_ids = self._used_source_ids(workspace_root)
        referenced_source_ids = {candidate.source_id for candidate in candidates}
        missing_references = sorted(used_source_ids - referenced_source_ids)

        self._write_bibtex(workspace_root, candidates)
        self._insert_section_citations(
            workspace_root,
            referenced_source_ids,
            citation_context,
        )
        self._write_audit_report(
            workspace_root,
            candidates,
            used_source_ids,
            missing_references,
            citation_context,
        )
        Coordinator(workspace_root).emit(
            "references.failed" if missing_references else "references.ready",
            source="ReferenceManager",
        )

    def _registered_source_ids(self, workspace_root: Path) -> set[str]:
        return {
            str(item.get("source_id"))
            for item in read_json(workspace_root / "data" / "source_registry.json", [])
            if isinstance(item, dict) and item.get("source_id")
        }

    def _registered_candidates(
        self,
        workspace_root: Path,
        registered_source_ids: set[str],
    ) -> list[CitationCandidate]:
        candidates: list[CitationCandidate] = []
        for item in read_json(workspace_root / "data" / "citation_candidates.json", []):
            if not isinstance(item, dict) or item.get("source_id") not in registered_source_ids:
                continue
            candidates.append(CitationCandidate.model_validate(item))
        return candidates

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
                    source_id
                    for source_id in self._string_list(item.get("source_ids"))
                    if source_id not in PLACEHOLDER_SOURCE_IDS
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

    def _write_bibtex(self, workspace_root: Path, candidates: list[CitationCandidate]) -> None:
        bibtex = "\n\n".join(candidate.bibtex or "" for candidate in candidates if candidate.bibtex)
        bibtex = self._escape_bibtex_specials(bibtex)
        (workspace_root / "paper" / "references.bib").write_text(
            bibtex + ("\n" if bibtex else ""),
            encoding="utf-8",
        )

    @staticmethod
    def _escape_bibtex_specials(text: str) -> str:
        # Escape LaTeX specials inside field VALUES only (the inner `{...}` of
        # title/url/note/...). Real search-derived values contain `&`, `_`, `%`,
        # etc. which are hard LaTeX errors ("Misplaced alignment tab",
        # "Missing $ inserted"). Citation keys live outside these braces
        # (`@misc{web_001,`) so they are never matched and stay intact.
        specials = ("&", "%", "#", "_", "$")

        def _escape_value(match: re.Match[str]) -> str:
            value = match.group(1)
            for char in specials:
                value = re.sub(r"(?<!\\)" + re.escape(char), "\\" + char, value)
            return "{" + value + "}"

        return re.sub(r"\{([^{}]*)\}", _escape_value, text)

    def _insert_section_citations(
        self,
        workspace_root: Path,
        referenced_source_ids: set[str],
        citation_context: CitationContext,
    ) -> None:
        section_dir = workspace_root / "paper" / "sections"
        if not section_dir.exists():
            return
        for section in section_dir.glob("*.tex"):
            text = section.read_text(encoding="utf-8")
            updated = text
            for source_id in sorted(referenced_source_ids):
                token = f"source_id={source_id}"
                cite = citation_context.cite_command([source_id]) or f"\\cite{{{source_id}}}"
                if token in updated and cite not in updated:
                    updated = updated.replace(token, f"{token} {cite}")
            if updated != text:
                section.write_text(updated, encoding="utf-8")

    def _write_audit_report(
        self,
        workspace_root: Path,
        candidates: list[CitationCandidate],
        used_source_ids: set[str],
        missing_references: list[str],
        citation_context: CitationContext,
    ) -> None:
        lines = [
            "# Reference Audit Report",
            "",
            f"Registered bibliography entries: {len(candidates)}",
            f"Used source IDs: {len(used_source_ids)}",
            f"Missing references: {len(missing_references)}",
            "",
            "## Missing References",
            *(f"- `{source_id}`" for source_id in missing_references),
            "" if missing_references else "- None.",
            "",
            "## Source To Bibliography Mapping",
            *self._source_mapping_lines(candidates, citation_context),
            "",
        ]
        (workspace_root / "review" / "reference_audit_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    def _source_mapping_lines(
        self,
        candidates: list[CitationCandidate],
        citation_context: CitationContext,
    ) -> list[str]:
        if not candidates:
            return ["- None."]
        lines = []
        for candidate in candidates:
            title = citation_context.source_title(candidate.source_id) or candidate.title
            key = citation_context.bibtex_key_for_source(candidate.source_id) or candidate.source_id
            suffix = f" ({title})" if title else ""
            lines.append(f"- `{candidate.source_id}` -> `{key}`{suffix}")
        return lines

    def _string_list(self, value: Any) -> set[str]:
        if not isinstance(value, list):
            return set()
        return {str(item) for item in value if str(item).strip()}
