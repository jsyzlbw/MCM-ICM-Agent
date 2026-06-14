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
                "from mcm_agent.solver_modules.forecasting import linear_trend_forecast",
                "from mcm_agent.solver_modules.network import shortest_path_table",
                "from mcm_agent.solver_modules.optimization import allocate_by_priority",
                "from mcm_agent.solver_modules.simulation import monte_carlo_scenarios",
                "",
                "workspace = Path.cwd()",
                f"df = pd.read_csv(workspace / {processed_relative!r})",
                f"selected_routes = {selected_routes!r}",
                "route_metric_payload = {}",
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
                "if 'forecasting_model' in selected_routes and len(numeric.columns) >= 2:",
                "    time_column = 'period' if 'period' in df.columns else numeric.columns[0]",
                "    target_column = 'demand' if 'demand' in df.columns else numeric.columns[-1]",
                "    forecast, forecast_metrics = linear_trend_forecast(",
                "        df, time_column=time_column, target_column=target_column, periods=3",
                "    )",
                "    forecast.to_csv(workspace / 'results/forecast_results.csv', index=False)",
                "    route_metric_payload.update({f'forecast_{key}': value for key, value in forecast_metrics.items()})",
                "if 'monte_carlo_simulation' in selected_routes and not numeric.empty:",
                "    base_value = float(numeric.mean().mean())",
                "    simulation_metrics = monte_carlo_scenarios(",
                "        base_value=base_value, relative_std=0.1, iterations=1000, seed=42",
                "    )",
                "    (workspace / 'results/simulation_summary.json').write_text(",
                "        json.dumps(simulation_metrics, indent=2), encoding='utf-8'",
                "    )",
                "    route_metric_payload.update({f'simulation_{key}': value for key, value in simulation_metrics.items()})",
                "if 'network_flow_graph' in selected_routes and {'source', 'target', 'cost'}.issubset(df.columns):",
                "    path_table = shortest_path_table(",
                "        df, source=str(df.iloc[0]['source']), target=str(df.iloc[-1]['target'])",
                "    )",
                "    path_table.to_csv(workspace / 'results/network_paths.csv', index=False)",
                "    route_metric_payload['shortest_path_cost'] = float(path_table.iloc[0]['path_cost'])",
                "    route_metric_payload['shortest_path_edge_count'] = float(path_table.iloc[0]['edge_count'])",
                "df.to_csv(workspace / 'results/problem1_results.csv', index=False)",
                "numeric = df.select_dtypes(include='number')",
                "metrics = {",
                "    'row_count': int(len(df)),",
                "    'column_count': int(len(df.columns)),",
                "    'numeric_column_count': int(len(numeric.columns)),",
                "}",
                "if not numeric.empty:",
                "    metrics['numeric_mean'] = float(numeric.mean().mean())",
                "metrics.update(route_metric_payload)",
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
        route_metrics = self._route_metrics(result_path, selected_routes, metrics)
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

    def _route_metrics(
        self,
        result_path: Path,
        selected_routes: list[str],
        metrics: dict[str, object] | None = None,
    ) -> dict[str, dict[str, object]]:
        frame = pd.read_csv(result_path)
        numeric = frame.select_dtypes(include="number")
        route_metrics: dict[str, dict[str, object]] = {}
        metrics = metrics or {}
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
                self._copy_metric_prefix(route_metrics, metrics, "forecast_", route_id)
                if "forecast_training_mae" not in route_metrics:
                    value = float(len(frame))
                    route_metrics["forecast_observation_count"] = {"route_id": route_id, "value": value}
            elif route_id == "monte_carlo_simulation":
                self._copy_metric_prefix(route_metrics, metrics, "simulation_", route_id)
                if "simulation_p95" not in route_metrics:
                    value = float(numeric.std().mean()) if not numeric.empty else 0.0
                    route_metrics["scenario_variability_index"] = {"route_id": route_id, "value": value}
            elif route_id == "network_flow_graph":
                if "shortest_path_cost" in metrics:
                    route_metrics["shortest_path_cost"] = {
                        "route_id": route_id,
                        "value": metrics["shortest_path_cost"],
                    }
                if "shortest_path_edge_count" in metrics:
                    route_metrics["shortest_path_edge_count"] = {
                        "route_id": route_id,
                        "value": metrics["shortest_path_edge_count"],
                    }
                if "shortest_path_cost" not in route_metrics:
                    value = float(len(frame.columns))
                    route_metrics["network_attribute_count"] = {"route_id": route_id, "value": value}
            elif route_id == "multi_objective_decision":
                value = float(len(numeric.columns))
                route_metrics["objective_proxy_count"] = {"route_id": route_id, "value": value}
        return route_metrics

    def _copy_metric_prefix(
        self,
        route_metrics: dict[str, dict[str, object]],
        metrics: dict[str, object],
        prefix: str,
        route_id: str,
    ) -> None:
        for key, value in metrics.items():
            if key.startswith(prefix):
                route_metrics[key] = {"route_id": route_id, "value": value}

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
            "forecasting_model": {
                "route_id": "forecasting_model",
                "module": "mcm_agent.solver_modules.forecasting",
                "method": "linear_trend_forecast",
            },
            "monte_carlo_simulation": {
                "route_id": "monte_carlo_simulation",
                "module": "mcm_agent.solver_modules.simulation",
                "method": "monte_carlo_scenarios",
            },
            "network_flow_graph": {
                "route_id": "network_flow_graph",
                "module": "mcm_agent.solver_modules.network",
                "method": "shortest_path_table",
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
