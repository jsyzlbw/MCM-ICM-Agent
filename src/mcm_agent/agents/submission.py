from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


class SubmissionPackager:
    def package(self, workspace_root: Path) -> bool:
        final_dir = workspace_root / "final_submission"
        final_dir.mkdir(parents=True, exist_ok=True)
        blockers = self._blockers(workspace_root)
        if blockers:
            (final_dir / "submission_blocked.md").write_text(
                "# Submission Blocked\n\n" + "\n".join(f"- {blocker}" for blocker in blockers) + "\n",
                encoding="utf-8",
            )
            return False

        self._write_ai_use_report(final_dir)
        self._write_submission_checklist(workspace_root, final_dir)
        manifest = self._write_submission_manifest(workspace_root, final_dir)
        source_zip = final_dir / "source_code.zip"
        with ZipFile(source_zip, "w", ZIP_DEFLATED) as archive:
            for relative_root in [
                "code",
                "results",
                "figures/source",
                "data/source_registry.json",
                "data/data_lineage.json",
                "data/retrieval_log.jsonl",
                "review/reference_audit_report.md",
                "review/source_audit_report.md",
                "review/figure_quality_report.md",
                "final_submission/submission_manifest.json",
            ]:
                path = workspace_root / relative_root
                if path.is_dir():
                    for file in path.rglob("*"):
                        if file.is_file():
                            archive.write(file, file.relative_to(workspace_root))
                elif path.exists():
                    archive.write(path, path.relative_to(workspace_root))

        with ZipFile(final_dir / "submission_package.zip", "w", ZIP_DEFLATED) as archive:
            archive.write(workspace_root / "paper" / "main.pdf", "final_paper.pdf")
            archive.write(final_dir / "AI_use_report.md", "AI_use_report.md")
            archive.write(final_dir / "submission_checklist.md", "submission_checklist.md")
            archive.write(manifest, "submission_manifest.json")
            archive.write(source_zip, "source_code.zip")
        return True

    def _blockers(self, workspace_root: Path) -> list[str]:
        blockers: list[str] = []
        unresolved = (workspace_root / "unresolved_issues.md").read_text(encoding="utf-8")
        if "[[UNRESOLVED:" in unresolved:
            blockers.append("Unresolved placeholders remain.")
        fact_report = workspace_root / "review" / "fact_regression_report.md"
        if fact_report.exists() and "critical" in fact_report.read_text(encoding="utf-8"):
            blockers.append("Critical fact regression remains.")
        reviewer_report = workspace_root / "review" / "reviewer_report.md"
        if reviewer_report.exists() and "Blocked." in reviewer_report.read_text(encoding="utf-8"):
            blockers.append("Reviewer blocked submission.")
        reference_audit = workspace_root / "review" / "reference_audit_report.md"
        if reference_audit.exists() and "Missing references: 0" not in reference_audit.read_text(
            encoding="utf-8"
        ):
            blockers.append("Reference audit has missing references.")
        if not (workspace_root / "paper" / "main.pdf").exists():
            blockers.append("paper/main.pdf is missing.")
        for figure in read_json(workspace_root / "figures" / "figure_registry.json", []):
            if figure.get("type") == "data_plot" and figure.get("status") != "approved":
                blockers.append(f"Data figure is not approved: {figure.get('figure_id')}")
        return blockers

    def _write_ai_use_report(self, final_dir: Path) -> None:
        (final_dir / "AI_use_report.md").write_text(
            "\n".join(
                [
                    "# AI Use Report",
                    "",
                    "## Tools Used",
                    "- MCM Agent reference implementation.",
                    "",
                    "## Human Decisions",
                    "- User checkpoints and revisions are recorded in the workspace.",
                    "",
                    "## AI-Assisted Steps",
                    "- Document parsing, planning, coding, writing, visualization, and review.",
                    "",
                    "## Verification Steps",
                    "- Evidence registry, source registry, figure registry, and fact regression checks.",
                    "",
                    "## External Services",
                    "- UShallPass is used only as academic style humanization with fact regression checking when configured.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _write_submission_checklist(self, workspace_root: Path, final_dir: Path) -> None:
        checklist = [
            "# Submission Checklist",
            "",
            f"- Paper PDF: `{(workspace_root / 'paper' / 'main.pdf').exists()}`",
            f"- Source registry: `{(workspace_root / 'data' / 'source_registry.json').exists()}`",
            f"- Data lineage: `{(workspace_root / 'data' / 'data_lineage.json').exists()}`",
            f"- Evidence registry: `{(workspace_root / 'results' / 'evidence_registry.json').exists()}`",
            f"- Reference audit: `{(workspace_root / 'review' / 'reference_audit_report.md').exists()}`",
            f"- Figure registry: `{(workspace_root / 'figures' / 'figure_registry.json').exists()}`",
            "",
        ]
        (final_dir / "submission_checklist.md").write_text(
            "\n".join(checklist),
            encoding="utf-8",
        )

    def _write_submission_manifest(self, workspace_root: Path, final_dir: Path) -> Path:
        route_summary = read_json(workspace_root / "results" / "model_route_summary.json", {})
        figures = read_json(workspace_root / "figures" / "figure_registry.json", [])
        model_routes = route_summary.get("selected_routes", []) if isinstance(route_summary, dict) else []
        manifest_path = final_dir / "submission_manifest.json"
        write_json(
            manifest_path,
            {
                "paper": "paper/main.pdf",
                "package": "final_submission/submission_package.zip",
                "source_archive": "final_submission/source_code.zip",
                "model_routes": model_routes if isinstance(model_routes, list) else [],
                "figure_ids": [
                    str(item.get("figure_id"))
                    for item in figures
                    if isinstance(item, dict) and item.get("figure_id")
                ],
                "audit_files": [
                    relative_path
                    for relative_path in [
                        "data/source_registry.json",
                        "data/data_lineage.json",
                        "data/retrieval_log.jsonl",
                        "results/model_metrics.json",
                        "results/model_route_summary.json",
                        "results/evidence_registry.json",
                        "review/reference_audit_report.md",
                        "review/source_audit_report.md",
                        "review/figure_quality_report.md",
                        "review/fact_regression_report.md",
                        "review/reviewer_report.md",
                    ]
                    if (workspace_root / relative_path).exists()
                ],
            },
        )
        return manifest_path
