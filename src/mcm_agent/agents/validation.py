from __future__ import annotations

from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.utils.json_io import read_json, write_json


class ValidationAgent:
    def run(self, workspace_root: Path) -> None:
        metrics = read_json(workspace_root / "results" / "model_metrics.json", {})
        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
        blocking_issues: list[str] = []

        evidence_sources = {
            (item.get("source_path"), item.get("evidence_id")) for item in evidence
        }
        for metric_key in metrics:
            has_evidence = any(
                source_path == "results/model_metrics.json" and str(evidence_id).endswith(metric_key)
                for source_path, evidence_id in evidence_sources
            )
            if not has_evidence:
                blocking_issues.append(f"Missing evidence for metric `{metric_key}`.")

        for item in evidence:
            source_path = item.get("source_path")
            if source_path and not (workspace_root / source_path).exists():
                blocking_issues.append(f"Evidence source does not exist: `{source_path}`.")

        write_json(
            workspace_root / "results" / "robustness_checks.json",
            {"blocking_issue_count": len(blocking_issues)},
        )
        (workspace_root / "results" / "sensitivity_analysis.csv").write_text(
            "parameter,delta,result_change\nbaseline,0,0\n",
            encoding="utf-8",
        )

        report = "\n".join(
            [
                "# Validation Report",
                "",
                "## Constraint Checks",
                "No explicit constraints registered in MVP baseline.",
                "",
                "## Metric Consistency",
                f"Checked {len(metrics)} metrics.",
                "",
                "## Evidence Coverage",
                f"Checked {len(evidence)} evidence items.",
                "",
                "## Sensitivity Analysis",
                "Baseline sensitivity file generated.",
                "",
                "## Robustness Checks",
                "Baseline robustness metadata generated.",
                "",
                "## Blocking Issues",
                *(f"- {issue}" for issue in blocking_issues),
                "" if blocking_issues else "- None.",
                "",
            ]
        )
        (workspace_root / "reports" / "validation_report.md").write_text(
            report,
            encoding="utf-8",
        )

        Coordinator(workspace_root).emit(
            "validation.failed" if blocking_issues else "validation.passed",
            source="ValidationAgent",
        )
