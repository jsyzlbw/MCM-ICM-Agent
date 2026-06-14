from __future__ import annotations

from pathlib import Path

from mcm_agent.core.gate_decision import GateDecision, record_gate_decision
from mcm_agent.utils.json_io import read_json


class ModelingPlanQualityAgent:
    REQUIRED_BINDINGS = {
        "forecasting_model": ["time_column", "target_column"],
        "network_flow_graph": ["source_column", "target_column", "cost_column"],
    }

    def run(self, workspace_root: Path) -> None:
        experiment_spec = read_json(workspace_root / "reports" / "experiment_spec.json", {})
        direction_lock = read_json(workspace_root / "discussion" / "direction_lock.json", {})
        feasibility_matrix = read_json(workspace_root / "data" / "data_feasibility_matrix.json", [])
        blocking_findings = []
        blocking_findings.extend(self._experiment_spec_issues(experiment_spec))
        blocking_findings.extend(
            self._data_alignment_issues(workspace_root, feasibility_matrix, direction_lock)
        )

        self._write_report(workspace_root, blocking_findings, feasibility_matrix, direction_lock)
        record_gate_decision(
            workspace_root,
            "modeling_gate.json",
            GateDecision(
                gate_id="modeling_quality_gate",
                status="fail" if blocking_findings else "pass",
                failure_reason="weak_model" if blocking_findings else None,
                repair_stage="modeling_council" if blocking_findings else None,
                blocking_findings=blocking_findings,
            ),
        )

    def _experiment_spec_issues(self, experiment_spec: object) -> list[str]:
        if not isinstance(experiment_spec, dict):
            return ["Experiment spec is missing or invalid."]
        experiments = experiment_spec.get("experiments", [])
        if not isinstance(experiments, list) or not experiments:
            return ["Experiment spec has no selected experiments."]
        issues = []
        for experiment in experiments:
            if not isinstance(experiment, dict):
                continue
            route_id = str(experiment.get("route_id", "unknown_route"))
            metrics = experiment.get("metrics", [])
            expected_outputs = experiment.get("expected_outputs", [])
            if not isinstance(metrics, list) or not metrics:
                issues.append(f"Experiment `{route_id}` has no machine-readable metrics.")
            if not isinstance(expected_outputs, list) or not expected_outputs:
                issues.append(f"Experiment `{route_id}` has no expected outputs.")
            bindings = experiment.get("column_bindings", {})
            if not isinstance(bindings, dict):
                bindings = {}
            for binding in self.REQUIRED_BINDINGS.get(route_id, []):
                if not bindings.get(binding):
                    issues.append(f"Missing required model data binding `{route_id}.{binding}`.")
        return issues

    def _data_alignment_issues(
        self,
        workspace_root: Path,
        feasibility_matrix: object,
        direction_lock: object,
    ) -> list[str]:
        adopted_strategy = ""
        if isinstance(direction_lock, dict):
            adopted_strategy = str(direction_lock.get("adopted_reframing_strategy", ""))
        if adopted_strategy in {"proxy_modeling", "user_provided_assumptions"}:
            return []
        if not isinstance(feasibility_matrix, list):
            return []
        issues = []
        for row in feasibility_matrix:
            if not isinstance(row, dict):
                continue
            availability = row.get("availability")
            proxies = row.get("proxy_variables", [])
            if availability == "private_or_unavailable":
                issues.append(
                    "Private or unavailable data need "
                    f"`{row.get('target_dataset', 'unknown')}` has no adopted reframing option."
                )
            if availability == "unknown" and not proxies and not self._has_attachments(workspace_root):
                issues.append(
                    "Unknown data need "
                    f"`{row.get('target_dataset', 'unknown')}` has no trusted data coverage or proxy plan."
                )
        return issues

    def _has_attachments(self, workspace_root: Path) -> bool:
        return any((workspace_root / "input" / "attachments").glob("*"))

    def _write_report(
        self,
        workspace_root: Path,
        blocking_findings: list[str],
        feasibility_matrix: object,
        direction_lock: object,
    ) -> None:
        lines = [
            "# Modeling Quality Report",
            "",
            "## Gate Status",
            "fail" if blocking_findings else "pass",
            "",
            "## Blocking Findings",
        ]
        if blocking_findings:
            lines.extend(f"- {finding}" for finding in blocking_findings)
        else:
            lines.append("- None.")
        lines.extend(["", "## Data Feasibility Rows"])
        if isinstance(feasibility_matrix, list) and feasibility_matrix:
            for row in feasibility_matrix:
                if isinstance(row, dict):
                    lines.append(
                        f"- {row.get('need_id', 'need')}: "
                        f"{row.get('target_dataset', 'unknown')} "
                        f"({row.get('availability', 'unknown')})"
                    )
        else:
            lines.append("- No feasibility matrix available.")
        lines.extend(["", "## Direction Lock"])
        if isinstance(direction_lock, dict):
            lines.append(
                "- Adopted reframing strategy: "
                f"{direction_lock.get('adopted_reframing_strategy', '') or 'none'}"
            )
        else:
            lines.append("- No direction lock available.")
        (workspace_root / "reports" / "modeling_quality_report.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
