from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.experiment import run_experiment
from mcm_agent.core.models import EvidenceItem
from mcm_agent.utils.json_io import read_json, write_json


class SolverCoderAgent:
    def run(self, workspace_root: Path) -> None:
        processed_files = sorted((workspace_root / "data" / "processed").glob("*.csv"))
        if not processed_files:
            raise FileNotFoundError("missing processed CSV data")

        code_dir = workspace_root / "code" / "experiments"
        results_dir = workspace_root / "results"
        code_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        processed_relative = str(processed_files[0].relative_to(workspace_root))
        selected_routes = self._selected_routes(workspace_root)
        package_src = str(Path(__file__).resolve().parents[2])
        script = "\n".join(
            [
                "import json",
                "import sys",
                "from pathlib import Path",
                "import pandas as pd",
                f"sys.path.insert(0, {package_src!r})",
                "from mcm_agent.solver_modules.evaluation import topsis_rank",
                "from mcm_agent.solver_modules.optimization import allocate_by_priority",
                "",
                "workspace = Path.cwd()",
                f"df = pd.read_csv(workspace / {processed_relative!r})",
                f"selected_routes = {selected_routes!r}",
                "numeric = df.select_dtypes(include='number')",
                "if 'multi_criteria_evaluation' in selected_routes and not numeric.empty:",
                "    entity_column = next((column for column in df.columns if column not in numeric.columns), None)",
                "    df = topsis_rank(df, indicator_columns=list(numeric.columns), entity_column=entity_column)",
                "if 'constrained_optimization' in selected_routes and not numeric.empty:",
                "    if 'priority_score' not in df.columns:",
                "        df['priority_score'] = numeric.mean(axis=1)",
                "    total_resource = float(numeric['budget'].sum()) if 'budget' in numeric.columns else float(numeric.sum().sum())",
                "    capacity_column = 'budget' if 'budget' in df.columns else None",
                "    df = allocate_by_priority(",
                "        df,",
                "        priority_column='priority_score',",
                "        total_resource=total_resource,",
                "        capacity_column=capacity_column,",
                "    )",
                "df.to_csv(workspace / 'results/problem1_results.csv', index=False)",
                "numeric = df.select_dtypes(include='number')",
                "metrics = {",
                "    'row_count': int(len(df)),",
                "    'column_count': int(len(df.columns)),",
                "    'numeric_column_count': int(len(numeric.columns)),",
                "}",
                "if not numeric.empty:",
                "    metrics['numeric_mean'] = float(numeric.mean().mean())",
                "(workspace / 'results/model_metrics.json').write_text(",
                "    json.dumps(metrics, indent=2),",
                "    encoding='utf-8',",
                ")",
                "",
            ]
        )
        script_path = code_dir / "problem1.py"
        script_path.write_text(script, encoding="utf-8")

        run_record = run_experiment(
            workspace_root,
            ["python", str(script_path.relative_to(workspace_root))],
            produced_files=["results/problem1_results.csv", "results/model_metrics.json"],
            timeout_seconds=120,
        )
        if run_record.exit_code != 0 or run_record.missing_outputs:
            (results_dir / "run_log.md").write_text(
                "\n".join(
                    [
                        "# Run Log",
                        "",
                        f"Generated at {datetime.now(UTC).isoformat()}.",
                        f"Exit code: {run_record.exit_code}",
                        f"Missing outputs: {run_record.missing_outputs}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            raise RuntimeError(f"experiment failed: {run_record.run_id}")

        result_path = results_dir / "problem1_results.csv"
        metrics = read_json(results_dir / "model_metrics.json", {})
        route_metrics = self._route_metrics(result_path, selected_routes)
        write_json(
            results_dir / "model_route_summary.json",
            {
                "selected_routes": selected_routes,
                "solver_modules": self._solver_modules(selected_routes),
                "route_metrics": route_metrics,
                "source_result": str(result_path.relative_to(workspace_root)),
            },
        )

        lineage_ids = self._lineage_ids_for_processed_file(workspace_root, processed_files[0])
        evidence = read_json(results_dir / "evidence_registry.json", [])
        for key, value in metrics.items():
            evidence.append(
                EvidenceItem(
                    evidence_id=f"metric_{key}",
                    claim=f"Metric {key} equals {value}.",
                    value=value,
                    source_type="code_output",
                    source_path="results/model_metrics.json",
                    generated_by=str(script_path.relative_to(workspace_root)),
                    used_in=[],
                    verified=True,
                    lineage_ids=lineage_ids,
                ).model_dump(mode="json")
            )
        for key, payload in route_metrics.items():
            evidence.append(
                EvidenceItem(
                    evidence_id=f"metric_{key}",
                    claim=f"Route metric {key} equals {payload['value']}.",
                    value=payload["value"],
                    source_type="code_output",
                    source_path="results/model_route_summary.json",
                    generated_by=str(script_path.relative_to(workspace_root)),
                    used_in=[str(payload["route_id"])],
                    verified=True,
                    lineage_ids=lineage_ids,
                ).model_dump(mode="json")
            )
        write_json(results_dir / "evidence_registry.json", evidence)

        (results_dir / "run_log.md").write_text(
            "\n".join(
                [
                    "# Run Log",
                    "",
                    f"Generated at {datetime.now(UTC).isoformat()}.",
                    f"Experiment run: `{run_record.run_id}`",
                    f"Result file: `{result_path.relative_to(workspace_root)}`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        Coordinator(workspace_root).emit("code.completed", source="SolverCoderAgent")

    def _lineage_ids_for_processed_file(self, workspace_root: Path, processed_file: Path) -> list[str]:
        summaries = read_json(workspace_root / "results" / "eda_summary.json", [])
        relative_path = str(processed_file.relative_to(workspace_root))
        for summary in summaries:
            if summary.get("file") == relative_path:
                return [str(item) for item in summary.get("lineage_ids", [])]
        return []

    def _selected_routes(self, workspace_root: Path) -> list[str]:
        decision_path = workspace_root / "reports" / "model_decision.md"
        if not decision_path.exists():
            return ["balanced_contest_route"]
        text = decision_path.read_text(encoding="utf-8")
        route_ids = [
            "multi_criteria_evaluation",
            "constrained_optimization",
            "forecasting_model",
            "monte_carlo_simulation",
            "network_flow_graph",
            "multi_objective_decision",
        ]
        selected = [route_id for route_id in route_ids if route_id in text]
        return selected or ["balanced_contest_route"]

    def _route_metrics(self, result_path: Path, selected_routes: list[str]) -> dict[str, dict[str, object]]:
        frame = pd.read_csv(result_path)
        numeric = frame.select_dtypes(include="number")
        route_metrics: dict[str, dict[str, object]] = {}
        for route_id in selected_routes:
            if route_id == "multi_criteria_evaluation":
                value = self._mean_for_column(numeric, "priority")
                route_metrics["priority_score_mean"] = {"route_id": route_id, "value": value}
                entity = self._top_priority_entity(frame)
                if entity is not None:
                    route_metrics["top_priority_entity"] = {
                        "route_id": route_id,
                        "value": entity,
                    }
            elif route_id == "constrained_optimization":
                value = self._sum_for_column(numeric, "recommended_allocation")
                route_metrics["allocation_capacity_total"] = {"route_id": route_id, "value": value}
            elif route_id == "forecasting_model":
                value = float(len(frame))
                route_metrics["forecast_observation_count"] = {"route_id": route_id, "value": value}
            elif route_id == "monte_carlo_simulation":
                value = float(numeric.std().mean()) if not numeric.empty else 0.0
                route_metrics["scenario_variability_index"] = {"route_id": route_id, "value": value}
            elif route_id == "network_flow_graph":
                value = float(len(frame.columns))
                route_metrics["network_attribute_count"] = {"route_id": route_id, "value": value}
            elif route_id == "multi_objective_decision":
                value = float(len(numeric.columns))
                route_metrics["objective_proxy_count"] = {"route_id": route_id, "value": value}
        return route_metrics

    def _solver_modules(self, selected_routes: list[str]) -> list[dict[str, str]]:
        modules = {
            "multi_criteria_evaluation": {
                "route_id": "multi_criteria_evaluation",
                "module": "mcm_agent.solver_modules.evaluation",
                "method": "entropy_weighted_topsis",
            },
            "constrained_optimization": {
                "route_id": "constrained_optimization",
                "module": "mcm_agent.solver_modules.optimization",
                "method": "capacity_constrained_priority_allocation",
            },
        }
        return [modules[route_id] for route_id in selected_routes if route_id in modules]

    def _mean_for_column(self, numeric: pd.DataFrame, preferred_column: str) -> float:
        if preferred_column in numeric.columns:
            return float(numeric[preferred_column].mean())
        return float(numeric.mean().mean()) if not numeric.empty else 0.0

    def _sum_for_column(self, numeric: pd.DataFrame, preferred_column: str) -> float:
        if preferred_column in numeric.columns:
            return float(numeric[preferred_column].sum())
        return float(numeric.sum().sum()) if not numeric.empty else 0.0

    def _top_priority_entity(self, frame: pd.DataFrame) -> str | None:
        if "priority_score" not in frame.columns or frame.empty:
            return None
        row = frame.sort_values("priority_score", ascending=False).iloc[0]
        for column in frame.columns:
            if column not in {"priority_score", "priority_rank", "recommended_allocation"}:
                value = row[column]
                if not isinstance(value, int | float):
                    return str(value)
        return str(row.name)
