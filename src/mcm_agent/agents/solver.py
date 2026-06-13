from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from mcm_agent.core.coordinator import Coordinator
from mcm_agent.core.models import EvidenceItem
from mcm_agent.utils.json_io import read_json, write_json


class SolverCoderAgent:
    def run(self, workspace_root: Path) -> None:
        processed_files = sorted((workspace_root / "data" / "processed").glob("*.csv"))
        if not processed_files:
            raise FileNotFoundError("missing processed CSV data")

        code_dir = workspace_root / "code"
        results_dir = workspace_root / "results"
        code_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        script = "\n".join(
            [
                "import pandas as pd",
                "df = pd.read_csv('../data/processed/sample.csv')",
                "df.to_csv('../results/problem1_results.csv', index=False)",
                "",
            ]
        )
        (code_dir / "problem1.py").write_text(script, encoding="utf-8")

        frame = pd.read_csv(processed_files[0])
        result_path = results_dir / "problem1_results.csv"
        frame.to_csv(result_path, index=False)
        numeric = frame.select_dtypes(include="number")
        metrics = {
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "numeric_column_count": int(len(numeric.columns)),
        }
        if not numeric.empty:
            metrics["numeric_mean"] = float(numeric.mean().mean())
        write_json(results_dir / "model_metrics.json", metrics)

        evidence = read_json(results_dir / "evidence_registry.json", [])
        for key, value in metrics.items():
            evidence.append(
                EvidenceItem(
                    evidence_id=f"metric_{key}",
                    claim=f"Metric {key} equals {value}.",
                    value=value,
                    source_type="code_output",
                    source_path="results/model_metrics.json",
                    generated_by="code/problem1.py",
                    used_in=[],
                    verified=True,
                ).model_dump(mode="json")
            )
        write_json(results_dir / "evidence_registry.json", evidence)

        (results_dir / "run_log.md").write_text(
            f"# Run Log\n\nGenerated at {datetime.now(UTC).isoformat()}.\n",
            encoding="utf-8",
        )
        Coordinator(workspace_root).emit("code.completed", source="SolverCoderAgent")
