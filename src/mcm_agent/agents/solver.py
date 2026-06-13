from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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
        script = "\n".join(
            [
                "import json",
                "from pathlib import Path",
                "import pandas as pd",
                "",
                "workspace = Path.cwd()",
                f"df = pd.read_csv(workspace / {processed_relative!r})",
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
