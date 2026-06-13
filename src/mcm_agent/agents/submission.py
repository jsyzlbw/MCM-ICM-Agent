from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from mcm_agent.utils.json_io import read_json


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
        source_zip = final_dir / "source_code.zip"
        with ZipFile(source_zip, "w", ZIP_DEFLATED) as archive:
            for relative_root in [
                "code",
                "results",
                "figures/source",
                "data/source_registry.json",
                "data/retrieval_log.jsonl",
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
