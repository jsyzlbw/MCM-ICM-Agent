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
        schema_datasets: list[dict[str, object]] = []
        evidence = read_json(workspace_root / "results" / "evidence_registry.json", [])
        lineage_records = read_json(workspace_root / "data" / "data_lineage.json", [])

        for input_file in input_files:
            frame = pd.read_csv(input_file)
            output = processed_dir / input_file.name
            frame.to_csv(output, index=False)
            source_type = (
                "external_data"
                if input_file.is_relative_to(workspace_root / "data" / "external")
                else "attachment"
            )
            lineage_ids = self._lineage_ids_for_input(workspace_root, input_file, lineage_records)
            missing = int(frame.isna().sum().sum())
            summary = {
                "file": str(output.relative_to(workspace_root)),
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "missing_values": missing,
                "source_type": source_type,
                "lineage_ids": lineage_ids,
            }
            summaries.append(summary)
            schema_datasets.append(
                {
                    "file": str(output.relative_to(workspace_root)),
                    "columns": [self._column_profile(frame, column) for column in frame.columns],
                }
            )
            evidence.append(
                EvidenceItem(
                    evidence_id=f"eda_{input_file.stem}_row_count",
                    claim=f"{input_file.name} contains {len(frame)} rows after loading.",
                    value=int(len(frame)),
                    source_type=source_type,
                    source_path=str(input_file.relative_to(workspace_root)),
                    generated_by="DataEDAAgent",
                    used_in=[],
                    verified=True,
                    lineage_ids=lineage_ids,
                ).model_dump(mode="json")
            )

        write_json(workspace_root / "results" / "eda_summary.json", summaries)
        write_json(workspace_root / "results" / "schema_profile.json", {"datasets": schema_datasets})
        write_json(workspace_root / "results" / "evidence_registry.json", evidence)

        lines = ["# Data Profile", ""]
        for summary in summaries:
            lines.append(
                f"- `{summary['file']}`: {summary['rows']} rows, "
                f"{summary['columns']} columns, {summary['missing_values']} missing values"
            )
        lines.extend(["", "## Schema Profile"])
        for dataset in schema_datasets:
            lines.append(f"- `{dataset['file']}`")
            for column in dataset["columns"]:
                tags = ", ".join(column["semantic_tags"]) or "unclassified"
                lines.append(
                    f"  - `{column['name']}`: {column['dtype']}, "
                    f"missing_rate={column['missing_rate']}, tags={tags}"
                )
        (workspace_root / "reports" / "data_profile.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    def _column_profile(self, frame: pd.DataFrame, column: str) -> dict[str, object]:
        series = frame[column]
        return {
            "name": column,
            "dtype": str(series.dtype),
            "missing_count": int(series.isna().sum()),
            "missing_rate": float(series.isna().mean()) if len(series) else 0.0,
            "unique_count": int(series.nunique(dropna=True)),
            "semantic_tags": self._semantic_tags(column, series),
        }

    def _semantic_tags(self, column: str, series: pd.Series) -> list[str]:
        lowered = column.lower()
        tags: list[str] = []
        if lowered in {"year", "period", "time", "date", "month"} or any(
            token in lowered for token in ["year", "period", "time", "date", "month"]
        ):
            tags.append("time")
        if lowered in {"demand", "sales", "target", "value", "outcome"} or any(
            token in lowered for token in ["demand", "sales", "target", "outcome"]
        ):
            tags.append("target")
        if lowered in {"source", "origin", "from", "start"}:
            tags.append("source_node")
        if lowered in {"target", "destination", "to", "end"}:
            tags.append("target_node")
        if lowered in {"cost", "distance", "weight", "length", "travel_time"} or any(
            token in lowered for token in ["cost", "distance", "weight"]
        ):
            tags.append("cost")
        if lowered in {"budget", "capacity", "limit", "resource"} or any(
            token in lowered for token in ["budget", "capacity", "resource"]
        ):
            tags.append("capacity")
        if lowered in {"label", "class", "category", "risk_label", "target_class"} or any(
            token in lowered for token in ["label", "class", "category"]
        ):
            tags.append("label")
        if lowered in {"segment", "group", "region", "cluster"} or any(
            token in lowered for token in ["segment", "group", "region", "cluster"]
        ):
            tags.append("group")
        if lowered in {"arrival", "arrival_rate", "lambda"} or "arrival" in lowered:
            tags.append("arrival_rate")
        if lowered in {"service", "service_rate", "mu"} or "service" in lowered:
            tags.append("service_rate")
        if lowered in {"servers", "server_count", "counter", "capacity_count"} or any(
            token in lowered for token in ["server", "counter", "capacity_count"]
        ):
            tags.append("server_count")
        if pd.api.types.is_numeric_dtype(series) and "time" not in tags:
            tags.append("numeric_indicator")
        return tags

    def _lineage_ids_for_input(
        self,
        workspace_root: Path,
        input_file: Path,
        lineage_records: list[dict[str, object]],
    ) -> list[str]:
        relative_path = str(input_file.relative_to(workspace_root))
        return [
            str(record["datum_id"])
            for record in lineage_records
            if record.get("local_path") == relative_path
        ]
