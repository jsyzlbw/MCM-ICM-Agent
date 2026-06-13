from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.core.registry import ArtifactRegistry
from mcm_agent.providers.mineru import FakeMinerUProvider


class DocumentExtractionAgent:
    def __init__(self, mineru_provider: object | None = None) -> None:
        self.mineru_provider = mineru_provider or FakeMinerUProvider()

    def run(self, workspace_root: Path) -> None:
        problem_candidates = sorted((workspace_root / "input").glob("problem.*"))
        if not problem_candidates:
            raise FileNotFoundError("missing input/problem.*")

        parsed = self.mineru_provider.parse_document(problem_candidates[0], workspace_root / "parsed")

        report = "\n".join(
            [
                "# Extraction Quality Report",
                "",
                f"- Parser: `{self.mineru_provider.__class__.__name__}`",
                f"- Page count: `{parsed.page_count}`",
                f"- Warnings: `{len(parsed.warnings)}`",
                f"- Tables: `{len(parsed.table_paths)}`",
                f"- Images: `{len(parsed.image_paths)}`",
                f"- Formula file: `{parsed.formula_path}`",
                "",
            ]
        )
        (workspace_root / "reports" / "extraction_quality_report.md").write_text(
            report,
            encoding="utf-8",
        )

        registry = ArtifactRegistry(workspace_root / "artifact_registry.json")
        try:
            registry.add(
                ArtifactRecord(
                    artifact_id="parsed_problem_v1",
                    type="parsed_problem",
                    path="parsed/problem.md",
                    producer="DocumentExtractionAgent",
                    status=ArtifactStatus.APPROVED,
                    created_at=datetime.now(UTC),
                    quality_checks=["fake_parse_available"],
                )
            )
        except ValueError:
            registry.update_status("parsed_problem_v1", ArtifactStatus.APPROVED)

        Coordinator(workspace_root).emit(
            "document.parsed",
            payload={"artifact_ids": ["parsed_problem_v1"]},
            source="DocumentExtractionAgent",
        )
