from __future__ import annotations

import json
import math
from pathlib import Path

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.core.metrics_flatten import flatten_metrics
from mcm_agent.core.model_spec import read_model_spec
from mcm_agent.utils.json_io import read_json, write_json

# Metric name fragments that indicate a bounded [0,1] ratio-type metric.
_RATIO_HINTS = (
    "rate", "accuracy", "acc", "consistency", "r2", "r_squared",
    "precision", "recall", "f1", "auc", "score", "ratio", "fraction",
    "coverage", "pct", "percent",
)
# Minimum floor for ratio-type metrics; values at or below this are degenerate.
_RATIO_FLOOR = 0.05


class ValidationAgent:
    def run(self, workspace_root: Path) -> None:
        metrics = read_json(workspace_root / "results" / "model_metrics.json", {})
        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
        blocking_issues: list[str] = []

        evidence_sources = {
            (item.get("source_path"), item.get("evidence_id")) for item in evidence
        }
        # Check leaf (flattened) metrics — the solver may write nested per-subproblem dicts.
        for metric_key in flatten_metrics(metrics):
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

        # Validate the END STATE, not historical attempts: a failed self-repair / earlier
        # codegen attempt that a later run superseded must not block. Flag only outputs that
        # are STILL missing on disk now.
        for run in self._read_experiment_runs(workspace_root / "results" / "experiment_runs.jsonl"):
            still_missing = [
                output
                for output in run.get("missing_outputs", [])
                if not (workspace_root / str(output)).exists()
            ]
            if still_missing:
                blocking_issues.append(
                    f"Experiment run `{run.get('run_id', 'unknown')}` is missing outputs: {still_missing}."
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

        # --- Result-plausibility check ---
        plausibility_issues = self._check_result_plausibility(workspace_root, metrics)
        blocking_issues.extend(plausibility_issues)

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

    def _check_result_plausibility(
        self,
        workspace_root: Path,
        raw_metrics: object,
    ) -> list[str]:
        """Check that the primary metric is finite and within a sane band.

        Returns a (possibly empty) list of blocking issue strings.
        """
        flat = flatten_metrics(raw_metrics)
        if not flat:
            return []

        # Identify the primary metric name.
        primary_name = self._primary_metric_name(workspace_root, flat)
        if primary_name is None:
            return []

        value = flat.get(primary_name)
        if not isinstance(value, (int, float)):
            return []

        issues: list[str] = []
        is_ratio = any(hint in primary_name.lower() for hint in _RATIO_HINTS)

        if not math.isfinite(value):
            issues.append(
                f"Primary metric `{primary_name}` = {value} is not finite "
                f"(NaN/inf); result is implausible — re-solve required."
            )
        elif is_ratio:
            if value <= _RATIO_FLOOR:
                issues.append(
                    f"Primary metric `{primary_name}` = {value:.4g} is at or below "
                    f"the plausibility floor {_RATIO_FLOOR} for a ratio/accuracy metric; "
                    f"result is degenerate — re-solve required."
                )
            elif value > 1.0:
                issues.append(
                    f"Primary metric `{primary_name}` = {value:.4g} exceeds 1.0 for a "
                    f"ratio/accuracy metric; result is implausible — re-solve required."
                )
        else:
            # Non-ratio metric: only require finite (already checked) and nonzero.
            if value == 0:
                issues.append(
                    f"Primary metric `{primary_name}` = 0 is exactly zero; "
                    f"result is degenerate — re-solve required."
                )
        return issues

    def _primary_metric_name(
        self,
        workspace_root: Path,
        flat: dict[str, object],
    ) -> str | None:
        """Return the primary metric key to check.

        Strategy (in priority order):
        1. First metric listed in ModelSpec.metrics for the first subproblem,
           if the flattened key exists in ``flat``.
        2. First key in ``flat`` whose value is numeric (int or float).
        Returns None if no suitable key found.
        """
        spec = read_model_spec(workspace_root)
        if spec is not None:
            for sub in spec.subproblems:
                for metric_name in sub.metrics:
                    # The flatten step converts special chars to underscores.
                    from mcm_agent.core.metrics_flatten import _safe_key  # type: ignore[attr-defined]
                    flat_key = _safe_key(metric_name)
                    if flat_key in flat:
                        return flat_key
                    # Also try the raw name in case it happened to match.
                    if metric_name in flat:
                        return metric_name

        # Fallback: first numeric key in flat metrics.
        for key, value in flat.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return key
        return None

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
