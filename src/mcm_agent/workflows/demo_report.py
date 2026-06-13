from __future__ import annotations

import json
from pathlib import Path

from mcm_agent.utils.json_io import read_json


def build_demo_report(workspace: Path) -> str:
    stage_runs = _read_jsonl(workspace / "stage_runs.jsonl")
    figure_gate = read_json(workspace / "review" / "figure_gate.json", {})
    final_gate = read_json(workspace / "review" / "final_gate.json", {})
    metrics = read_json(workspace / "results" / "model_metrics.json", {})
    key_artifacts = [
        "paper/main.tex",
        "figures/fig_q1_prediction.pdf",
        "figures/fig_q1_prediction.svg",
        "review/figure_quality_report.md",
        "review/reviewer_report.md",
        "final_submission/AI_use_report.md",
    ]
    lines = [
        "# Demo Run Report",
        "",
        f"Workspace: `{workspace}`",
        f"Stage count: {len(stage_runs)}",
        f"Figure gate: {figure_gate.get('status', 'missing')}",
        f"Final gate: {final_gate.get('status', 'missing')}",
        "",
        "## Metrics",
    ]
    if metrics:
        lines.extend(f"- {key}: {value}" for key, value in sorted(metrics.items()))
    else:
        lines.append("- Missing `results/model_metrics.json`.")
    lines.extend(["", "## Key Artifacts"])
    for artifact in key_artifacts:
        lines.append(f"- `{artifact}`: {'present' if (workspace / artifact).exists() else 'missing'}")
    lines.extend(["", "## Last Stages"])
    for record in stage_runs[-8:]:
        lines.append(
            f"- `{record.get('stage_id')}`: {record.get('status')} -> {record.get('next_stage')}"
        )
    lines.append("")
    return "\n".join(lines)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records
