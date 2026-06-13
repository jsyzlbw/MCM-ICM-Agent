from __future__ import annotations

from pathlib import Path

import pandas as pd

from mcm_agent.core.models import EvidenceItem
from mcm_agent.utils.json_io import read_json, write_json


class DataEDAAgent:
    def run(self, workspace_root: Path) -> None:
        input_files = list((workspace_root / "input" / "attachments").glob("*.csv"))
        input_files.extend((workspace_root / "data" / "external").glob("*.csv"))
        processed_dir = workspace_root / "data" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        summaries: list[dict[str, object]] = []
        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])

        for input_file in input_files:
            frame = pd.read_csv(input_file)
            output = processed_dir / input_file.name
            frame.to_csv(output, index=False)
            missing = int(frame.isna().sum().sum())
            summary = {
                "file": str(output.relative_to(workspace_root)),
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "missing_values": missing,
            }
            summaries.append(summary)
            evidence.append(
                EvidenceItem(
                    evidence_id=f"eda_{input_file.stem}_row_count",
                    claim=f"{input_file.name} contains {len(frame)} rows after loading.",
                    value=int(len(frame)),
                    source_type="attachment",
                    source_path=str(input_file.relative_to(workspace_root)),
                    generated_by="DataEDAAgent",
                    used_in=[],
                    verified=True,
                ).model_dump(mode="json")
            )

        write_json(workspace_root / "results" / "eda_summary.json", summaries)
        write_json(workspace_root / "results" / "evidence_registry.json", evidence)

        lines = ["# Data Profile", ""]
        for summary in summaries:
            lines.append(
                f"- `{summary['file']}`: {summary['rows']} rows, "
                f"{summary['columns']} columns, {summary['missing_values']} missing values"
            )
        (workspace_root / "reports" / "data_profile.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
