from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from mcm_agent.utils.json_io import append_jsonl
from mcm_agent.utils.subprocesses import run_command


class ExperimentRunRecord(BaseModel):
    run_id: str
    command: list[str]
    exit_code: int
    stdout_path: str
    stderr_path: str
    produced_files: list[str] = Field(default_factory=list)
    missing_outputs: list[str] = Field(default_factory=list)
    duration_seconds: float
    started_at: datetime
    finished_at: datetime


def run_experiment(
    workspace_root: Path,
    command: list[str],
    *,
    produced_files: list[str],
    timeout_seconds: int,
) -> ExperimentRunRecord:
    runs_dir = workspace_root / "results" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    stdout_path = runs_dir / f"{run_id}.stdout.txt"
    stderr_path = runs_dir / f"{run_id}.stderr.txt"
    started_at = datetime.now(UTC)
    result = run_command(command, cwd=workspace_root, timeout_seconds=timeout_seconds)
    finished_at = datetime.now(UTC)

    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")
    missing_outputs = [
        relative_path
        for relative_path in produced_files
        if not (workspace_root / relative_path).exists()
    ]
    record = ExperimentRunRecord(
        run_id=run_id,
        command=result.command,
        exit_code=result.return_code,
        stdout_path=str(stdout_path.relative_to(workspace_root)),
        stderr_path=str(stderr_path.relative_to(workspace_root)),
        produced_files=produced_files,
        missing_outputs=missing_outputs,
        duration_seconds=result.duration_seconds,
        started_at=started_at,
        finished_at=finished_at,
    )
    append_jsonl(workspace_root / "results" / "experiment_runs.jsonl", record.model_dump(mode="json"))
    return record
