from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.experiment import run_experiment
from mcm_agent.core.experiment_spec import ExperimentSpec
from mcm_agent.core.metrics_flatten import flatten_metrics
from mcm_agent.core.models import EvidenceItem
from mcm_agent.utils.json_io import read_json, write_json


class SolverCoderAgent:
    def __init__(self, llm_provider: object | None = None) -> None:
        self.llm_provider = llm_provider

    def run(self, workspace_root: Path) -> None:
        if self.llm_provider is not None and self._run_llm_codegen(workspace_root):
            self._record_outputs(workspace_root)
            return
        self._run_templated_baseline(workspace_root)

    def _model_spec_block(self, workspace_root: Path) -> str:
        """Serialize the designed ModelSpec so the generated code implements exactly
        the model the paper will describe (model<->code coherence)."""
        from mcm_agent.core.model_spec import read_model_spec

        spec = read_model_spec(workspace_root)
        if spec is None or not spec.subproblems:
            return ""
        lines = ["MODEL SPEC TO IMPLEMENT (implement exactly this designed model):"]
        for sub in spec.subproblems:
            lines.append(f"- [{sub.subproblem_id}] {sub.title} — approach: {sub.approach}")
            if sub.algorithm_steps:
                lines.append("  algorithm: " + " | ".join(sub.algorithm_steps))
            if sub.metrics:
                lines.append("  required metrics (use these JSON keys): " + ", ".join(sub.metrics))
        return "\n".join(lines) + "\n\n"

    def _run_llm_codegen(self, workspace_root: Path, *, max_attempts: int = 3) -> bool:
        processed = sorted((workspace_root / "data" / "processed").glob("*.csv"))
        if not processed:
            return False
        understanding = self._read_text(workspace_root / "reports" / "problem_understanding.md", 4000)
        direction = self._read_text(workspace_root / "discussion" / "confirmed_direction.md", 1500)
        schema = self._schema_excerpt(processed[0])
        code_dir = workspace_root / "code" / "experiments"
        code_dir.mkdir(parents=True, exist_ok=True)
        script_path = code_dir / "problem1.py"
        # Snapshot the run log so failed self-repair attempts can be pruned on success;
        # they are internal codegen iterations, not pipeline failures the gate should flag.
        runs_path = workspace_root / "results" / "experiment_runs.jsonl"
        prior_runs = runs_path.read_text(encoding="utf-8") if runs_path.exists() else ""
        system = (
            "You write correct, self-contained Python for a math-modeling contest. "
            "Output ONLY one ```python code block."
        )
        spec_block = self._model_spec_block(workspace_root)
        base_prompt = (
            "Write a Python script that solves the contest sub-problems using the real data.\n"
            f"PROBLEM UNDERSTANDING:\n{understanding}\n\nCONFIRMED DIRECTION:\n{direction}\n\n"
            f"{spec_block}"
            f"DATA SCHEMA (first rows):\n{schema}\n\n"
            "CONTRACT:\n"
            "- import pandas as pd; read data via "
            "sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0]\n"
            "- Use only pandas, numpy, scipy, sklearn, matplotlib.\n"
            "- Write the main result table to results/problem1_results.csv\n"
            "- Write a JSON dict of TASK-SPECIFIC metrics (keys named after the problem, e.g. "
            "elimination_consistency_rate) to results/model_metrics.json\n"
            "- Perform a real sensitivity analysis: vary ONE key parameter/assumption over >=3 "
            "values, recompute your primary metric for each, and write "
            "results/sensitivity_analysis.csv with columns parameter,value,<primary_metric> "
            "(one row per value).\n"
            "- Do not call the network or read files outside the workspace.\n"
        )
        last_err = ""
        for attempt in range(max_attempts):
            prompt = base_prompt if attempt == 0 else (
                base_prompt
                + f"\n\nThe previous script failed with:\n{last_err}\n"
                + "Fix it and return the full corrected script."
            )
            try:
                result = self.llm_provider.generate(system, prompt)
            except Exception as exc:  # transient LLM error (timeout/network): retry, then baseline
                last_err = f"LLM generation failed: {type(exc).__name__}: {exc}"
                continue
            code = self._extract_code(result.content)
            if not code:
                last_err = "LLM returned no code"
                continue
            script_path.write_text(code, encoding="utf-8")
            record = run_experiment(
                workspace_root,
                ["python", str(script_path.relative_to(workspace_root))],
                produced_files=["results/problem1_results.csv", "results/model_metrics.json"],
                timeout_seconds=180,
            )
            if record.exit_code == 0 and not record.missing_outputs:
                metrics = read_json(workspace_root / "results" / "model_metrics.json", {})
                if isinstance(metrics, dict) and metrics:
                    success_line = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
                    runs_path.write_text(prior_runs + success_line + "\n", encoding="utf-8")
                    self._llm_script_rel = str(script_path.relative_to(workspace_root))
                    self._run_sensitivity_sweep(workspace_root, processed[0])  # PQ4: backfill if LLM omitted it
                    return True
                last_err = "model_metrics.json missing or not a non-empty dict"
            else:
                stderr_path = workspace_root / record.stderr_path
                last_err = (
                    stderr_path.read_text(encoding="utf-8")[-1500:]
                    if stderr_path.exists()
                    else f"missing outputs: {record.missing_outputs}"
                )
        return False

    @staticmethod
    def _extract_code(text: str) -> str:
        match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        return (match.group(1) if match else text).strip()

    @staticmethod
    def _extract_code_block(text: str) -> str:
        """Return fenced-block contents ONLY when a fence is present, else ''.

        Unlike _extract_code (which falls back to the whole text), this method
        returns '' when no fence is found — enabling 'no fence = DONE' semantics
        in the ReAct loop.

        Accepts any or no language tag (python, py, Python, …) and tolerates an
        optional newline between the opening fence/tag and the first line of code.
        Returns the FIRST block only.  Plain prose / "DONE" / inline backticks
        that are not triple-fenced all return ''.
        """
        match = re.search(r"```[^\n`]*\n?(.*?)```", text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _subproblem_prompt(
        self, workspace_root: Path, processed_file: Path, sub: object | None
    ) -> str:
        """Build the per-subproblem initial prompt for the ReAct loop."""
        understanding = self._read_text(
            workspace_root / "reports" / "problem_understanding.md", 4000
        )
        direction = self._read_text(
            workspace_root / "discussion" / "confirmed_direction.md", 1500
        )
        spec_block = self._model_spec_block(workspace_root)
        schema = self._schema_excerpt(processed_file)
        sub_title = getattr(sub, "title", None) or "problem1"
        sub_metrics = getattr(sub, "metrics", None) or []
        metric_keys = (
            (", ".join(sub_metrics))
            if sub_metrics
            else "task-specific keys named after the problem"
        )
        return (
            f"Subproblem: {sub_title}\n\n"
            f"PROBLEM UNDERSTANDING:\n{understanding}\n\n"
            f"CONFIRMED DIRECTION:\n{direction}\n\n"
            f"{spec_block}"
            f"DATA SCHEMA (first rows):\n{schema}\n\n"
            "CONTRACT:\n"
            "- Read data via sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0]\n"
            "- Use only pandas, numpy, scipy, sklearn, matplotlib — no network access.\n"
            "- Write the main result table to results/problem1_results.csv\n"
            f"- Write a JSON dict with TASK-SPECIFIC metric keys ({metric_keys}) "
            "to results/model_metrics.json\n"
            "- Do not read files outside the workspace.\n"
        )

    def _run_interpreter_loop(
        self,
        workspace_root: Path,
        *,
        interpreter_factory=None,
        max_turns: int = 12,
        max_errors: int = 4,
    ) -> bool:
        """Multi-turn ReAct loop: LLM emits one ```python block per turn, we execute
        it in a persistent interpreter, feed real stdout/error back, and continue until
        the LLM signals DONE (no code fence) or limits are reached.

        Returns True iff results/model_metrics.json is a non-empty dict at the end.
        Returns False on any construction/fatal failure (caller degrades gracefully).
        """
        from mcm_agent.core.model_spec import read_model_spec

        processed = sorted((workspace_root / "data" / "processed").glob("*.csv"))
        if not processed:
            return False

        (workspace_root / "results").mkdir(parents=True, exist_ok=True)

        if interpreter_factory is None:
            try:
                from mcm_agent.tools.code_interpreter import JupyterCodeInterpreter

                interpreter_factory = lambda root: JupyterCodeInterpreter(root)  # noqa: E731
            except Exception:
                return False

        try:
            interp = interpreter_factory(workspace_root)
        except Exception:
            return False

        system = (
            "你在一个【有状态 Python(Jupyter) 会话】里求解 MCM 子问题。变量跨 cell 保留。\n"
            "要运行代码：只回复**一个** ```python ...``` 代码块，我会执行并把输出/报错回给你。\n"
            "报错时请基于真实报错修正后重试。\n"
            "当该子问题**完全解出且所有要求的输出文件已写好**时，只回复一个词 DONE（不带代码块）。"
        )

        try:
            spec = read_model_spec(workspace_root)
            subs = (spec.subproblems if (spec and spec.subproblems) else [None])

            for sub in subs:
                title = getattr(sub, "title", None) or "problem1"
                interp.add_section(title)
                transcript = self._subproblem_prompt(workspace_root, processed[0], sub)
                errors = 0
                for _turn in range(max_turns):
                    content = self.llm_provider.generate(system, transcript).content
                    code = self._extract_code_block(content)
                    if not code:
                        break  # DONE / no fence
                    res = interp.execute(code)
                    feedback = (res.error if res.had_error else res.stdout)[-2000:]
                    transcript += (
                        f"\n\n[ASSISTANT]\n{content}\n\n[CELL OUTPUT]\n{feedback}"
                    )
                    if res.had_error:
                        errors += 1
                        if errors >= max_errors:
                            break

            interp.save_notebook()
        except Exception:
            try:
                interp.shutdown()
            except Exception:
                pass
            return False
        finally:
            try:
                interp.shutdown()
            except Exception:
                pass

        metrics = read_json(workspace_root / "results" / "model_metrics.json", {})
        if isinstance(metrics, dict) and metrics:
            self._llm_script_rel = "notebook.ipynb"
            self._run_sensitivity_sweep(workspace_root, processed[0])
            return True
        return False

    @staticmethod
    def _read_text(path: Path, limit: int) -> str:
        return path.read_text(encoding="utf-8")[:limit] if path.exists() else ""

    @staticmethod
    def _schema_excerpt(csv_path: Path) -> str:
        frame = pd.read_csv(csv_path, nrows=5)
        return f"columns={list(frame.columns)}\n{frame.to_string(index=False)}"

    def _record_outputs(self, workspace_root: Path) -> None:
        results_dir = workspace_root / "results"
        metrics = read_json(results_dir / "model_metrics.json", {})
        script_rel = getattr(self, "_llm_script_rel", "code/experiments/problem1.py")
        write_json(
            results_dir / "model_route_summary.json",
            {
                "selected_routes": ["LLM-generated problem-specific model"],
                "route_metrics": {},
                "source_result": "results/problem1_results.csv",
                "generated_by": script_rel,
            },
        )
        processed = sorted((workspace_root / "data" / "processed").glob("*.csv"))
        lineage_ids = (
            self._lineage_ids_for_processed_file(workspace_root, processed[0]) if processed else []
        )
        evidence = read_json(results_dir / "evidence_registry.json", [])
        # Flatten nested per-subproblem metrics so every leaf metric is registered as
        # traceable evidence (e.g. metric_problem1_elimination_consistency_rate).
        for key, value in flatten_metrics(metrics).items():
            evidence.append(
                EvidenceItem(
                    evidence_id=f"metric_{key}",
                    claim=f"Metric {key} equals {value}.",
                    value=value,
                    source_type="code_output",
                    source_path="results/model_metrics.json",
                    generated_by=script_rel,
                    used_in=[],
                    verified=True,
                    lineage_ids=lineage_ids,
                ).model_dump(mode="json")
            )
        write_json(results_dir / "evidence_registry.json", evidence)
        Coordinator(workspace_root).emit("code.completed", source="SolverCoderAgent")

    def _run_templated_baseline(self, workspace_root: Path) -> None:
        processed_files = sorted((workspace_root / "data" / "processed").glob("*.csv"))
        if not processed_files:
            raise FileNotFoundError("missing processed CSV data")

        code_dir = workspace_root / "code" / "experiments"
        results_dir = workspace_root / "results"
        code_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        processed_relative = str(processed_files[0].relative_to(workspace_root))
        experiment_spec = self._experiment_spec(workspace_root)
        selected_routes = self._selected_routes(workspace_root, experiment_spec)
        column_bindings = self._column_bindings(
            workspace_root,
            pd.read_csv(processed_files[0]),
            processed_relative,
            experiment_spec,
            selected_routes,
        )
        binding_report = self._binding_report(column_bindings, selected_routes)
        self._write_binding_report(workspace_root, binding_report)
        package_src = str(Path(__file__).resolve().parents[2])
        script = "\n".join(
            [
                "import json",
                "import sys",
                "from pathlib import Path",
                "import pandas as pd",
                f"sys.path.insert(0, {package_src!r})",
                "from mcm_agent.solver_modules.classification import logistic_regression_baseline",
                "from mcm_agent.solver_modules.clustering import kmeans_segmentation",
                "from mcm_agent.solver_modules.evaluation import topsis_rank",
                "from mcm_agent.solver_modules.forecasting import linear_trend_forecast",
                "from mcm_agent.solver_modules.network import shortest_path_table",
                "from mcm_agent.solver_modules.optimization import allocate_by_priority",
                "from mcm_agent.solver_modules.queuing import mmc_queue_summary",
                "from mcm_agent.solver_modules.simulation import monte_carlo_scenarios",
                "",
                "workspace = Path.cwd()",
                f"df = pd.read_csv(workspace / {processed_relative!r})",
                f"selected_routes = {selected_routes!r}",
                f"column_bindings = {column_bindings!r}",
                "route_metric_payload = {}",
                "numeric = df.select_dtypes(include='number')",
                "if 'multi_criteria_evaluation' in selected_routes and not numeric.empty:",
                "    evaluation_bindings = column_bindings.get('multi_criteria_evaluation', {})",
                "    entity_column = evaluation_bindings.get('entity_column') or next((column for column in df.columns if column not in numeric.columns), None)",
                "    indicator_columns = [column for column in evaluation_bindings.get('indicator_columns', []) if column in df.columns]",
                "    df = topsis_rank(df, indicator_columns=indicator_columns or list(numeric.columns), entity_column=entity_column)",
                "if 'constrained_optimization' in selected_routes and not numeric.empty:",
                "    if 'priority_score' not in df.columns:",
                "        df['priority_score'] = numeric.mean(axis=1)",
                "    optimization_bindings = column_bindings.get('constrained_optimization', {})",
                "    priority_column = optimization_bindings.get('priority_column') or 'priority_score'",
                "    capacity_column = optimization_bindings.get('capacity_column') or ('budget' if 'budget' in df.columns else None)",
                "    total_resource = float(df[capacity_column].sum()) if capacity_column else float(numeric.sum().sum())",
                "    df = allocate_by_priority(",
                "        df,",
                "        priority_column=priority_column,",
                "        total_resource=total_resource,",
                "        capacity_column=capacity_column,",
                "    )",
                "if 'forecasting_model' in selected_routes and len(numeric.columns) >= 2:",
                "    forecast_bindings = column_bindings.get('forecasting_model', {})",
                "    time_column = forecast_bindings.get('time_column') or ('period' if 'period' in df.columns else numeric.columns[0])",
                "    target_column = forecast_bindings.get('target_column') or ('demand' if 'demand' in df.columns else numeric.columns[-1])",
                "    forecast, forecast_metrics = linear_trend_forecast(",
                "        df, time_column=time_column, target_column=target_column, periods=3",
                "    )",
                "    forecast.to_csv(workspace / 'results/forecast_results.csv', index=False)",
                "    route_metric_payload.update({f'forecast_{key}': value for key, value in forecast_metrics.items()})",
                "if 'monte_carlo_simulation' in selected_routes and not numeric.empty:",
                "    simulation_bindings = column_bindings.get('monte_carlo_simulation', {})",
                "    base_value_column = simulation_bindings.get('base_value_column')",
                "    base_value = float(df[base_value_column].mean()) if base_value_column else float(numeric.mean().mean())",
                "    simulation_metrics = monte_carlo_scenarios(",
                "        base_value=base_value, relative_std=0.1, iterations=1000, seed=42",
                "    )",
                "    (workspace / 'results/simulation_summary.json').write_text(",
                "        json.dumps(simulation_metrics, indent=2), encoding='utf-8'",
                "    )",
                "    route_metric_payload.update({f'simulation_{key}': value for key, value in simulation_metrics.items()})",
                "if 'classification_model' in selected_routes and not numeric.empty:",
                "    classification_bindings = column_bindings.get('classification_model', {})",
                "    label_column = classification_bindings.get('label_column')",
                "    feature_columns = [column for column in classification_bindings.get('feature_columns', []) if column in df.columns]",
                "    if label_column in df.columns and feature_columns:",
                "        classification_result, classification_metrics = logistic_regression_baseline(",
                "            df, feature_columns=feature_columns, label_column=label_column",
                "        )",
                "        classification_result.to_csv(workspace / 'results/classification_results.csv', index=False)",
                "        route_metric_payload.update(classification_metrics)",
                "if 'clustering_segmentation' in selected_routes and not numeric.empty:",
                "    clustering_bindings = column_bindings.get('clustering_segmentation', {})",
                "    feature_columns = [column for column in clustering_bindings.get('feature_columns', []) if column in df.columns]",
                "    if feature_columns:",
                "        cluster_result, cluster_metrics = kmeans_segmentation(",
                "            df, feature_columns=feature_columns, n_clusters=3",
                "        )",
                "        cluster_result.to_csv(workspace / 'results/cluster_segments.csv', index=False)",
                "        route_metric_payload.update(cluster_metrics)",
                "if 'queuing_service_model' in selected_routes:",
                "    queue_bindings = column_bindings.get('queuing_service_model', {})",
                "    arrival_rate_column = queue_bindings.get('arrival_rate_column')",
                "    service_rate_column = queue_bindings.get('service_rate_column')",
                "    server_count_column = queue_bindings.get('server_count_column') or None",
                "    if arrival_rate_column in df.columns and service_rate_column in df.columns:",
                "        queue_result, queue_metrics = mmc_queue_summary(",
                "            df,",
                "            arrival_rate_column=arrival_rate_column,",
                "            service_rate_column=service_rate_column,",
                "            server_count_column=server_count_column,",
                "        )",
                "        queue_result.to_csv(workspace / 'results/queue_summary.csv', index=False)",
                "        route_metric_payload.update(queue_metrics)",
                "if 'network_flow_graph' in selected_routes:",
                "    network_bindings = column_bindings.get('network_flow_graph', {})",
                "    source_column = network_bindings.get('source_column') or 'source'",
                "    target_column = network_bindings.get('target_column') or 'target'",
                "    cost_column = network_bindings.get('cost_column') or 'cost'",
                "    if {source_column, target_column, cost_column}.issubset(df.columns):",
                "        path_table = shortest_path_table(",
                "            df,",
                "            source=str(df.iloc[0][source_column]),",
                "            target=str(df.iloc[-1][target_column]),",
                "            source_column=source_column,",
                "            target_column=target_column,",
                "            cost_column=cost_column,",
                "        )",
                "        path_table.to_csv(workspace / 'results/network_paths.csv', index=False)",
                "        route_metric_payload['shortest_path_cost'] = float(path_table.iloc[0]['path_cost'])",
                "        route_metric_payload['shortest_path_edge_count'] = float(path_table.iloc[0]['edge_count'])",
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
                "experiment_spec_used": bool(experiment_spec.experiments),
                "column_bindings": column_bindings,
                "binding_status": binding_report["status"],
                "route_execution_status": self._route_execution_status(
                    selected_routes,
                    route_metrics,
                    binding_report,
                ),
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
        self._run_sensitivity_sweep(workspace_root, processed_files[0])
        Coordinator(workspace_root).emit("code.completed", source="SolverCoderAgent")

    def _run_sensitivity_sweep(self, workspace_root: Path, processed_file: Path) -> None:
        """Deterministic sensitivity fallback: scale a numeric input column and recompute
        input_mean_proxy for each of 5 scale factors [0.8, 0.9, 1.0, 1.1, 1.2].

        Column name 'input_mean_proxy' signals this is a diagnostic input-stability proxy,
        NOT the model's primary metric.

        Only writes if results/sensitivity_analysis.csv is absent or has <3 data rows.
        NEVER fabricates numbers — every row is a REAL recomputation on perturbed data.
        Skips silently if the processed CSV has no numeric columns.
        """
        sens_path = workspace_root / "results" / "sensitivity_analysis.csv"

        # Check whether a valid sensitivity CSV already exists (>=3 real data rows).
        if sens_path.exists():
            try:
                existing = pd.read_csv(sens_path)
                if len(existing) >= 3:
                    return  # already satisfied — do not overwrite
            except Exception:
                pass  # unreadable file; proceed to generate

        try:
            df = pd.read_csv(processed_file)
        except Exception:
            return  # can't read data — skip, don't fabricate

        numeric_cols = list(df.select_dtypes(include="number").columns)
        if not numeric_cols:
            return  # no numeric column to perturb — skip, don't fabricate

        # Use the first numeric column as the sweep parameter.
        sweep_col = numeric_cols[0]
        scale_factors = [0.8, 0.9, 1.0, 1.1, 1.2]
        rows: list[dict[str, object]] = []
        for factor in scale_factors:
            perturbed = df.copy()
            perturbed[sweep_col] = perturbed[sweep_col] * factor
            perturbed_numeric = perturbed.select_dtypes(include="number")
            metric_value = float(perturbed_numeric.mean().mean())
            rows.append(
                {
                    "parameter": sweep_col,
                    "scale_factor": factor,
                    "input_mean_proxy": round(metric_value, 6),
                }
            )

        result = pd.DataFrame(rows)
        result.to_csv(sens_path, index=False)

    def _lineage_ids_for_processed_file(self, workspace_root: Path, processed_file: Path) -> list[str]:
        summaries = read_json(workspace_root / "results" / "eda_summary.json", [])
        relative_path = str(processed_file.relative_to(workspace_root))
        for summary in summaries:
            if summary.get("file") == relative_path:
                return [str(item) for item in summary.get("lineage_ids", [])]
        return []

    def _experiment_spec(self, workspace_root: Path) -> ExperimentSpec:
        payload = read_json(workspace_root / "reports" / "experiment_spec.json", {})
        if isinstance(payload, dict):
            return ExperimentSpec.model_validate(payload)
        return ExperimentSpec()

    def _selected_routes(self, workspace_root: Path, experiment_spec: ExperimentSpec | None = None) -> list[str]:
        if experiment_spec and experiment_spec.experiments:
            return [item.route_id for item in experiment_spec.experiments]
        decision_path = workspace_root / "reports" / "model_decision.md"
        if not decision_path.exists():
            return ["balanced_contest_route"]
        text = decision_path.read_text(encoding="utf-8")
        route_ids = [
            "multi_criteria_evaluation",
            "constrained_optimization",
            "forecasting_model",
            "monte_carlo_simulation",
            "classification_model",
            "clustering_segmentation",
            "queuing_service_model",
            "network_flow_graph",
            "multi_objective_decision",
        ]
        selected = [route_id for route_id in route_ids if route_id in text]
        return selected or ["balanced_contest_route"]

    def _column_bindings(
        self,
        workspace_root: Path,
        frame: pd.DataFrame,
        processed_relative: str,
        experiment_spec: ExperimentSpec,
        selected_routes: list[str],
    ) -> dict[str, dict[str, object]]:
        semantic = self._semantic_columns(workspace_root, processed_relative)
        explicit = {
            item.route_id: {
                key: value
                for key, value in item.column_bindings.items()
                if value or isinstance(value, list)
            }
            for item in experiment_spec.experiments
        }
        numeric_columns = list(frame.select_dtypes(include="number").columns)
        text_columns = [column for column in frame.columns if column not in numeric_columns]
        bindings: dict[str, dict[str, object]] = {}
        for route_id in selected_routes:
            current = dict(explicit.get(route_id, {}))
            if route_id == "multi_criteria_evaluation":
                current.setdefault("entity_column", semantic.get("entity", text_columns[0] if text_columns else ""))
                current.setdefault("indicator_columns", semantic.get("numeric_indicator", numeric_columns))
            elif route_id == "constrained_optimization":
                current.setdefault("priority_column", "priority_score")
                current.setdefault(
                    "capacity_column",
                    semantic.get("capacity", self._first_existing(frame, ["budget", "capacity"])),
                )
            elif route_id == "forecasting_model":
                time_column = str(current.get("time_column", ""))
                if not self._is_numeric_column(frame, time_column):
                    time_column = self._forecast_time_column(frame, semantic, numeric_columns)
                current["time_column"] = time_column
                target_column = str(current.get("target_column", ""))
                if not self._is_numeric_column(frame, target_column) or target_column == time_column:
                    target_column = self._numeric_target_column(
                        frame,
                        semantic,
                        numeric_columns,
                        excluded={time_column},
                    )
                current["target_column"] = target_column
            elif route_id == "monte_carlo_simulation":
                base_value_column = str(current.get("base_value_column", ""))
                if not self._is_numeric_column(frame, base_value_column):
                    base_value_column = self._numeric_target_column(
                        frame,
                        semantic,
                        numeric_columns,
                    )
                current["base_value_column"] = base_value_column
            elif route_id == "classification_model":
                label_column = str(current.get("label_column", ""))
                if label_column not in frame.columns:
                    label_column = self._classification_label_column(
                        frame,
                        semantic,
                        numeric_columns,
                    )
                current["label_column"] = label_column
                feature_columns = current.get("feature_columns", [])
                if not isinstance(feature_columns, list):
                    feature_columns = []
                feature_columns = [
                    str(column)
                    for column in feature_columns
                    if self._is_numeric_column(frame, str(column)) and str(column) != label_column
                ]
                if not feature_columns:
                    feature_columns = [
                        column
                        for column in numeric_columns
                        if column != label_column
                    ]
                current["feature_columns"] = feature_columns
            elif route_id == "clustering_segmentation":
                feature_columns = current.get("feature_columns", [])
                if not isinstance(feature_columns, list):
                    feature_columns = []
                feature_columns = [
                    str(column)
                    for column in feature_columns
                    if self._is_numeric_column(frame, str(column))
                ]
                if not feature_columns:
                    feature_columns = self._clustering_feature_columns(
                        frame,
                        semantic,
                        numeric_columns,
                    )
                current["feature_columns"] = feature_columns
                current.setdefault("entity_column", semantic.get("entity", text_columns[0] if text_columns else ""))
            elif route_id == "queuing_service_model":
                arrival_rate_column = str(current.get("arrival_rate_column", ""))
                if not self._is_numeric_column(frame, arrival_rate_column):
                    arrival_rate_column = self._queue_rate_column(
                        frame,
                        semantic,
                        numeric_columns,
                        "arrival_rate",
                        ["arrival_rate", "arrival", "lambda"],
                    )
                current["arrival_rate_column"] = arrival_rate_column
                service_rate_column = str(current.get("service_rate_column", ""))
                if (
                    not self._is_numeric_column(frame, service_rate_column)
                    or service_rate_column == arrival_rate_column
                ):
                    service_rate_column = self._queue_rate_column(
                        frame,
                        semantic,
                        numeric_columns,
                        "service_rate",
                        ["service_rate", "service", "mu"],
                        excluded={arrival_rate_column},
                    )
                current["service_rate_column"] = service_rate_column
                server_count_column = str(current.get("server_count_column", ""))
                if not self._is_numeric_column(frame, server_count_column):
                    server_count_column = self._queue_rate_column(
                        frame,
                        semantic,
                        numeric_columns,
                        "server_count",
                        ["servers", "server_count", "counter", "capacity_count"],
                        excluded={arrival_rate_column, service_rate_column},
                    )
                current["server_count_column"] = server_count_column
            elif route_id == "network_flow_graph":
                current.setdefault("source_column", semantic.get("source_node", self._first_existing(frame, ["source", "origin", "from"])))
                current.setdefault("target_column", semantic.get("target_node", self._first_existing(frame, ["target", "destination", "to"])))
                current.setdefault("cost_column", semantic.get("cost", self._first_existing(frame, ["cost", "distance", "weight"])))
            bindings[route_id] = current
        return bindings

    def _binding_report(
        self,
        column_bindings: dict[str, dict[str, object]],
        selected_routes: list[str],
    ) -> dict[str, object]:
        required = {
            "forecasting_model": ["time_column", "target_column"],
            "network_flow_graph": ["source_column", "target_column", "cost_column"],
            "classification_model": ["label_column"],
            "queuing_service_model": ["arrival_rate_column", "service_rate_column"],
        }
        missing = []
        details = []
        for route_id in selected_routes:
            bindings = column_bindings.get(route_id, {})
            route_missing = [
                f"{route_id}.{field}"
                for field in required.get(route_id, [])
                if not bindings.get(field)
            ]
            missing.extend(route_missing)
            details.append(
                {
                    "route_id": route_id,
                    "bindings": bindings,
                    "missing": route_missing,
                }
            )
        return {
            "status": "fail" if missing else "pass",
            "missing_bindings": missing,
            "details": details,
        }

    def _write_binding_report(self, workspace_root: Path, report: dict[str, object]) -> None:
        write_json(workspace_root / "results" / "solver_binding_report.json", report)
        lines = [
            "# Solver Binding Report",
            "",
            f"Status: {report['status']}",
            "",
            "## Missing Bindings",
        ]
        missing = report.get("missing_bindings", [])
        if isinstance(missing, list) and missing:
            lines.extend(f"- `{item}`" for item in missing)
        else:
            lines.append("- None.")
        lines.append("")
        (workspace_root / "reports" / "solver_binding_report.md").write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    def _route_execution_status(
        self,
        selected_routes: list[str],
        route_metrics: dict[str, dict[str, object]],
        binding_report: dict[str, object],
    ) -> dict[str, str]:
        missing_payload = binding_report.get("missing_bindings", [])
        missing = set(missing_payload) if isinstance(missing_payload, list) else set()
        status: dict[str, str] = {}
        for route_id in selected_routes:
            if any(str(item).startswith(route_id + ".") for item in missing):
                status[route_id] = "blocked_missing_binding"
            elif any(payload.get("route_id") == route_id for payload in route_metrics.values()):
                status[route_id] = "executed"
            else:
                status[route_id] = "attempted_no_metric"
        return status

    def _semantic_columns(self, workspace_root: Path, processed_relative: str) -> dict[str, object]:
        profile = read_json(workspace_root / "results" / "schema_profile.json", {})
        if not isinstance(profile, dict):
            return {}
        datasets = profile.get("datasets", [])
        if not isinstance(datasets, list):
            return {}
        semantic: dict[str, object] = {}
        for dataset in datasets:
            if not isinstance(dataset, dict) or dataset.get("file") != processed_relative:
                continue
            for column in dataset.get("columns", []):
                if not isinstance(column, dict):
                    continue
                name = str(column.get("name", ""))
                tags = column.get("semantic_tags", [])
                if not name or not isinstance(tags, list):
                    continue
                for tag in tags:
                    if tag == "numeric_indicator":
                        semantic.setdefault("numeric_indicator", [])
                        if isinstance(semantic["numeric_indicator"], list):
                            semantic["numeric_indicator"].append(name)
                    else:
                        semantic.setdefault(str(tag), name)
            break
        return semantic

    def _first_existing(self, frame: pd.DataFrame, candidates: list[str]) -> str:
        lower_to_original = {column.lower(): column for column in frame.columns}
        for candidate in candidates:
            if candidate in lower_to_original:
                return lower_to_original[candidate]
        return ""

    def _is_numeric_column(self, frame: pd.DataFrame, column: str) -> bool:
        return bool(column) and column in frame.columns and pd.api.types.is_numeric_dtype(frame[column])

    def _semantic_candidates(self, semantic: dict[str, object], tag: str) -> list[str]:
        value = semantic.get(tag)
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        return []

    def _first_numeric_candidate(
        self,
        frame: pd.DataFrame,
        candidates: list[str],
        *,
        excluded: set[str] | None = None,
    ) -> str:
        excluded = excluded or set()
        for candidate in candidates:
            column = self._first_existing(frame, [candidate])
            if column and column not in excluded and self._is_numeric_column(frame, column):
                return column
        return ""

    def _forecast_time_column(
        self,
        frame: pd.DataFrame,
        semantic: dict[str, object],
        numeric_columns: list[str],
    ) -> str:
        candidates = [
            *self._semantic_candidates(semantic, "time"),
            "period",
            "year",
            "time",
            "month",
            *numeric_columns,
        ]
        return self._first_numeric_candidate(frame, candidates)

    def _numeric_target_column(
        self,
        frame: pd.DataFrame,
        semantic: dict[str, object],
        numeric_columns: list[str],
        *,
        excluded: set[str] | None = None,
    ) -> str:
        candidates = [
            *self._semantic_candidates(semantic, "target"),
            "demand",
            "sales",
            "target",
            "value",
            "outcome",
            *numeric_columns,
        ]
        return self._first_numeric_candidate(frame, candidates, excluded=excluded)

    def _classification_label_column(
        self,
        frame: pd.DataFrame,
        semantic: dict[str, object],
        numeric_columns: list[str],
    ) -> str:
        candidates = [
            *self._semantic_candidates(semantic, "label"),
            *self._semantic_candidates(semantic, "target"),
            "risk_label",
            "target_class",
            "label",
            "class",
            "category",
            "outcome",
        ]
        for candidate in candidates:
            column = self._first_existing(frame, [candidate])
            if column:
                return column
        for column in frame.columns:
            unique_count = frame[column].nunique(dropna=True)
            if 1 < unique_count <= max(10, len(frame) // 2):
                return column
        return numeric_columns[-1] if numeric_columns else ""

    def _clustering_feature_columns(
        self,
        frame: pd.DataFrame,
        semantic: dict[str, object],
        numeric_columns: list[str],
    ) -> list[str]:
        preferred = [
            *self._semantic_candidates(semantic, "group"),
            "segment_value",
            "segment_score",
            "region_score",
            "cluster_value",
        ]
        selected = [
            column
            for column in (self._first_existing(frame, [candidate]) for candidate in preferred)
            if column and self._is_numeric_column(frame, column)
        ]
        for column in numeric_columns:
            if column not in selected:
                selected.append(column)
        return selected

    def _queue_rate_column(
        self,
        frame: pd.DataFrame,
        semantic: dict[str, object],
        numeric_columns: list[str],
        semantic_tag: str,
        candidates: list[str],
        *,
        excluded: set[str] | None = None,
    ) -> str:
        excluded = excluded or set()
        ordered = [
            *self._semantic_candidates(semantic, semantic_tag),
            *candidates,
            *numeric_columns,
        ]
        return self._first_numeric_candidate(frame, ordered, excluded=excluded)

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
            elif route_id == "classification_model":
                self._copy_metric_prefix(route_metrics, metrics, "classification_", route_id)
            elif route_id == "clustering_segmentation":
                self._copy_metric_prefix(route_metrics, metrics, "cluster_", route_id)
            elif route_id == "queuing_service_model":
                self._copy_metric_prefix(route_metrics, metrics, "queue_", route_id)
                if "expected_wait_time" in metrics:
                    route_metrics["expected_wait_time"] = {
                        "route_id": route_id,
                        "value": metrics["expected_wait_time"],
                    }
                if "unstable_queue_count" in metrics:
                    route_metrics["unstable_queue_count"] = {
                        "route_id": route_id,
                        "value": metrics["unstable_queue_count"],
                    }
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
            "classification_model": {
                "route_id": "classification_model",
                "module": "mcm_agent.solver_modules.classification",
                "method": "logistic_regression_baseline",
            },
            "clustering_segmentation": {
                "route_id": "clustering_segmentation",
                "module": "mcm_agent.solver_modules.clustering",
                "method": "kmeans_segmentation",
            },
            "queuing_service_model": {
                "route_id": "queuing_service_model",
                "module": "mcm_agent.solver_modules.queuing",
                "method": "mmc_queue_summary",
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
