from __future__ import annotations

import json
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
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

        for run in self._read_experiment_runs(workspace_root / "results" / "experiment_runs.jsonl"):
            run_id = run.get("run_id", "unknown")
            exit_code = run.get("exit_code", 0)
            missing_outputs = run.get("missing_outputs", [])
            if exit_code != 0 or missing_outputs:
                blocking_issues.append(
                    f"Experiment run `{run_id}` failed or missed outputs: {missing_outputs}."
                )

        binding_report = read_json(workspace_root / "results" / "solver_binding_report.json", {})
        binding_failure = False
        if isinstance(binding_report, dict) and binding_report.get("status") == "fail":
            binding_failure = True
            missing_bindings = binding_report.get("missing_bindings", [])
            if isinstance(missing_bindings, list):
                blocking_issues.append(
                    "Missing solver column bindings: "
                    + ", ".join(f"`{binding}`" for binding in missing_bindings)
                    + "."
                )

        sensitivity_rows = self._read_sensitivity_rows(
            workspace_root / "results" / "sensitivity_analysis.csv"
        )
        if not sensitivity_rows:
            # Honest empty file (header only) — never fabricate a baseline row.
            (workspace_root / "results" / "sensitivity_analysis.csv").write_text(
                "parameter,value,result\n", encoding="utf-8"
            )
        # Missing sensitivity is reported (and scored by MockJudge) but does NOT block,
        # so the baseline/offline path still completes.
        sensitivity_params = sorted({row[0] for row in sensitivity_rows})
        write_json(
            workspace_root / "results" / "robustness_checks.json",
            {
                "blocking_issue_count": len(blocking_issues),
                "sensitivity_row_count": len(sensitivity_rows),
                "sensitivity_parameters": sensitivity_params,
            },
        )
        sensitivity_summary = (
            f"Recorded {len(sensitivity_rows)} sensitivity rows over parameters: "
            + ", ".join(sensitivity_params)
            + "."
            if sensitivity_rows
            else "No sensitivity rows were produced by the solver."
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
                sensitivity_summary,
                "",
                "## Robustness Checks",
                f"{len(blocking_issues)} blocking issue(s) detected during validation.",
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
        record_gate_decision(
            workspace_root,
            "validation_gate.json",
            GateDecision(
                gate_id="validation_gate",
                status="fail" if blocking_issues else "pass",
                failure_reason="weak_model" if binding_failure else ("bad_results" if blocking_issues else None),
                repair_stage=self._repair_stage_for_blockers(
                    binding_failure=binding_failure,
                    blocking_issues=blocking_issues,
                ),
                blocking_findings=blocking_issues,
            ),
        )

        Coordinator(workspace_root).emit(
            "validation.failed" if blocking_issues else "validation.passed",
            source="ValidationAgent",
        )

    def _repair_stage_for_blockers(
        self,
        *,
        binding_failure: bool,
        blocking_issues: list[str],
    ) -> str | None:
        if not blocking_issues:
            return None
        if binding_failure:
            return "modeling_council"
        return "solver_coder"

    def _read_sensitivity_rows(self, path: Path) -> list[tuple[str, ...]]:
        """Real solver-produced sensitivity rows (header skipped; legacy 'baseline'
        placeholder ignored)."""
        if not path.exists():
            return []
        rows: list[tuple[str, ...]] = []
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines[1:]:  # skip header
            cells = tuple(cell.strip() for cell in line.split(","))
            if cells and cells[0] and cells[0].lower() != "baseline":
                rows.append(cells)
        return rows

    def _read_experiment_runs(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        runs: list[dict[str, object]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                runs.append(
                    {
                        "run_id": f"invalid_json_line_{line_number}",
                        "exit_code": 1,
                        "missing_outputs": ["invalid experiment run record"],
                    }
                )
                continue
            if isinstance(payload, dict):
                runs.append(payload)
        return runs
