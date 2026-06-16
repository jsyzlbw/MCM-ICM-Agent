from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mcm_agent.utils.json_io import read_json, write_json

RunFn = Callable[[Callable[[object], str]], None]


@dataclass
class RunHandle:
    workspace_id: str
    workspace_root: Path
    status: str = "running"  # running | paused | done | failed | stopped
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    control_signal: str | None = None
    resume_from: str | None = None
    pending_checkpoint_id: str | None = None
    until_stage: str | None = None
    error: str | None = None
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    _logs: deque = field(default_factory=lambda: deque(maxlen=500))
    _log_cursor: int = 0
    _seq: int = 0

    def log(self, message: str, *, level: str = "info", stage_id: str = "") -> None:
        self._seq += 1
        self._logs.append(
            {"seq": self._seq, "level": level, "stage_id": stage_id,
             "message": message, "ts": datetime.now(UTC).isoformat()}
        )

    def drain_logs(self) -> list[dict]:
        items = [item for item in self._logs if item["seq"] > self._log_cursor]
        if items:
            self._log_cursor = items[-1]["seq"]
        return items

    def duration_seconds(self) -> float:
        return (datetime.now(UTC) - self.started_at).total_seconds()

    def display_status(self) -> str:
        if self.status == "running" and self.stop_event.is_set():
            return "stopping"
        return self.status


class RunRegistry:
    class AlreadyRunningError(RuntimeError):
        pass

    def __init__(self) -> None:
        self._runs: dict[str, RunHandle] = {}
        self._lock = threading.Lock()

    def get(self, workspace_id: str) -> RunHandle | None:
        return self._runs.get(workspace_id)

    def is_running(self, workspace_id: str) -> bool:
        handle = self._runs.get(workspace_id)
        return handle is not None and handle.status == "running"

    def start(
        self,
        workspace_id: str,
        workspace_root: Path,
        *,
        run_fn: RunFn,
        auto_approve: bool,
        pause_after: set[str],
        until_stage: str | None = None,
    ) -> RunHandle:
        with self._lock:
            if self.is_running(workspace_id):
                raise self.AlreadyRunningError(workspace_id)
            handle = RunHandle(workspace_id=workspace_id, workspace_root=workspace_root, until_stage=until_stage)
            self._runs[workspace_id] = handle

        def controller(record: object) -> str:
            if handle.stop_event.is_set():
                handle.control_signal = "stop"
                handle.resume_from = getattr(record, "next_stage", None)
                handle.log(f"stop requested after {getattr(record, 'stage_id', '?')}")
                return "stop"
            stage_id = getattr(record, "stage_id", "")
            next_stage = getattr(record, "next_stage", None)
            handle.log(f"completed {stage_id}", stage_id=stage_id)
            if (not auto_approve) and stage_id in pause_after and next_stage is not None:
                handle.control_signal = "pause"
                handle.resume_from = next_stage
                handle.pending_checkpoint_id = _create_pending_checkpoint(workspace_root)
                handle.log(f"paused after {stage_id}, awaiting approval", level="warn")
                return "pause"
            return "continue"

        def thread_main() -> None:
            try:
                run_fn(controller)
                if handle.control_signal == "stop":
                    handle.status = "stopped"
                elif handle.control_signal == "pause":
                    handle.status = "paused"
                else:
                    handle.status = "done"
            except Exception as exc:  # noqa: BLE001 - surface to GUI as failed run
                handle.status = "failed"
                handle.error = str(exc)
                handle.log(f"run failed: {exc}", level="error")

        thread = threading.Thread(target=thread_main, daemon=True)
        handle.thread = thread
        thread.start()
        return handle

    def stop(self, workspace_id: str) -> bool:
        handle = self._runs.get(workspace_id)
        if handle is None:
            return False
        handle.stop_event.set()
        return True


def _create_pending_checkpoint(workspace_root: Path) -> str:
    path = workspace_root / "task_state.json"
    state = read_json(path, {})
    if not isinstance(state, dict):
        state = {}
    checkpoint_id = f"checkpoint_{uuid4().hex[:12]}"
    state.setdefault("checkpoints", []).append(
        {
            "checkpoint_id": checkpoint_id,
            "status": "pending",
            "user_message": "",
            "approved_artifacts": [],
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    state["updated_at"] = datetime.now(UTC).isoformat()
    write_json(path, state)
    return checkpoint_id
