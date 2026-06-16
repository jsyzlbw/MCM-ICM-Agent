# Phase 1: Backend Workflow Control API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a GUI (or curl) start / resume / stop a workflow run, approve pause checkpoints, and stream live progress over SSE — all file-backed and testable with fake providers.

**Architecture:** Add one small control hook to `StageExecutor.run_until_complete` (it currently runs straight through). Thread that hook through `run_mvp_workflow`/`resume_mvp_workflow`. Add an in-process, thread-based `RunRegistry` that owns the background run, a cooperative stop flag, a pause-checkpoint mechanism, and a log buffer. Expose run/resume/stop/approve/run-status/events/logs as FastAPI routes mounted by the existing `mcm-agent gui` server. No new agent code; no node; no `progress_events.jsonl` (events derive from existing `stage_runs.jsonl` + `task_state.json` + the run's log buffer).

**Tech Stack:** Python, FastAPI, Starlette `StreamingResponse` (SSE), `threading`, Pydantic, pytest + `fastapi.testclient.TestClient`.

This plan implements §4.2–§4.5, §7–§10 of `docs/superpowers/specs/2026-06-16-frontend-gui-design.md`. Frontend (Phase 2), knowledge base (Phase 3), and discussion screen (Phase 4) are separate plans.

---

## File Structure

- Modify `src/mcm_agent/core/stage_executor.py` — add optional `controller` callback to `run_until_complete`.
- Modify `src/mcm_agent/workflows/mvp.py` — pass `controller` through `run_mvp_workflow` and `resume_mvp_workflow`.
- Create `src/mcm_agent/server/run_registry.py` — `RunRegistry`, `RunHandle`, the controller factory, pause-checkpoint helper.
- Create `src/mcm_agent/server/routes_workflow.py` — `create_workflow_router(workspace_base, registry, config_path)`.
- Modify `src/mcm_agent/server/app.py` — build a `RunRegistry` and mount the workflow router.
- Create `tests/test_stage_executor_controller.py` — unit test for the hook.
- Create `tests/test_run_registry.py` — unit tests for the registry (complete / pause / stop) with an injected fake `run_fn`.
- Create `tests/test_server_workflow_control.py` — HTTP integration tests (bounded demo run, run-status, events, approve→resume).

---

## Task 1: Executor control hook

**Files:**
- Modify: `src/mcm_agent/core/stage_executor.py`
- Test: `tests/test_stage_executor_controller.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_executor_controller.py
from datetime import UTC, datetime

from mcm_agent.core.stage_executor import StageExecutor, StageResult


def _topology(tmp_path):
    # linear: a -> b -> c
    (tmp_path / "workflow_topology.json").write_text(
        '{"edges":['
        '{"from_node":"a","to_node":"b","condition":"pass"},'
        '{"from_node":"b","to_node":"c","condition":"pass"}]}',
        encoding="utf-8",
    )
    (tmp_path / "task_state.json").write_text(
        '{"workspace_id":"w","current_phase":"initialized",'
        f'"created_at":"{datetime.now(UTC).isoformat()}",'
        f'"updated_at":"{datetime.now(UTC).isoformat()}"}}',
        encoding="utf-8",
    )


def _handlers():
    return {
        "a": lambda root: StageResult(outputs=["a.txt"]),
        "b": lambda root: StageResult(outputs=["b.txt"]),
        "c": lambda root: StageResult(outputs=["c.txt"]),
    }


def test_controller_stop_halts_after_current_stage(tmp_path):
    _topology(tmp_path)
    executor = StageExecutor(tmp_path, handlers=_handlers())

    seen = []

    def controller(record):
        seen.append(record.stage_id)
        return "stop" if record.stage_id == "a" else "continue"

    records = executor.run_until_complete("a", controller=controller)

    assert [r.stage_id for r in records] == ["a"]
    assert seen == ["a"]


def test_controller_continue_runs_to_end(tmp_path):
    _topology(tmp_path)
    executor = StageExecutor(tmp_path, handlers=_handlers())
    records = executor.run_until_complete("a", controller=lambda record: "continue")
    assert [r.stage_id for r in records] == ["a", "b", "c"]


def test_controller_pause_breaks_loop(tmp_path):
    _topology(tmp_path)
    executor = StageExecutor(tmp_path, handlers=_handlers())

    def controller(record):
        return "pause" if record.stage_id == "b" else "continue"

    records = executor.run_until_complete("a", controller=controller)
    assert [r.stage_id for r in records] == ["a", "b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage_executor_controller.py -v`
Expected: FAIL — `run_until_complete() got an unexpected keyword argument 'controller'`.

- [ ] **Step 3: Add the controller parameter and hook**

In `src/mcm_agent/core/stage_executor.py`, `Callable` is **already imported** at the top (`from collections.abc import Callable`) — no import change needed.

Change the `run_until_complete` signature and loop. Replace the entire existing `run_until_complete` method with:

```python
    def run_until_complete(
        self,
        start_stage: str,
        *,
        terminal_stage: str | None = None,
        max_steps: int = 100,
        repeated_gate_limit: int = 3,
        controller: Callable[[StageRunRecord], str] | None = None,
    ) -> list[StageRunRecord]:
        records: list[StageRunRecord] = []
        gate_failures: dict[tuple[str, str], int] = {}
        current_stage: str | None = start_stage
        for _ in range(max_steps):
            if current_stage is None:
                break
            record = self.run_stage(current_stage)
            records.append(record)
            gate_decision = self._gate_decision_for_stage(record.stage_id)
            if gate_decision is not None and not gate_decision.passed:
                failure_reason = gate_decision.failure_reason or "unknown"
                key = (gate_decision.gate_id, failure_reason)
                gate_failures[key] = gate_failures.get(key, 0) + 1
                if gate_failures[key] >= repeated_gate_limit:
                    self._mark_blocked(gate_decision)
                    raise RepeatedGateFailureError(
                        gate_decision.gate_id,
                        failure_reason,
                        gate_decision.repair_stage,
                    )
            if terminal_stage is not None and current_stage == terminal_stage:
                break
            if controller is not None and controller(record) != "continue":
                break
            current_stage = record.next_stage
        else:
            raise RuntimeError(f"stage execution exceeded max_steps={max_steps}")
        return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage_executor_controller.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/core/stage_executor.py tests/test_stage_executor_controller.py
git commit -m "feat: add control hook to stage executor run loop"
```

---

## Task 2: Thread the controller through the workflow entrypoints

**Files:**
- Modify: `src/mcm_agent/workflows/mvp.py:82-138`
- Test: `tests/test_stage_executor_controller.py` (add one workflow-level test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stage_executor_controller.py`:

```python
def test_resume_mvp_workflow_passes_controller(tmp_path):
    from mcm_agent.core.workspace import create_workspace
    from mcm_agent.workflows.demo_fixtures import create_demo_inputs
    from mcm_agent.workflows.mvp import resume_mvp_workflow
    from mcm_agent.core.models import TaskInput

    create_workspace(tmp_path / "ws")
    problem, attachments, idea, skills = create_demo_inputs(tmp_path / "demo_inputs")

    stopped_after = []

    def controller(record):
        stopped_after.append(record.stage_id)
        return "stop" if record.stage_id == "intake" else "continue"

    resume_mvp_workflow(
        tmp_path / "ws",
        TaskInput(problem_file=problem, attachments=attachments, user_idea_file=idea),
        supervisor_skills_dir=skills,
        auto_approve=True,
        from_stage="intake",
        controller=controller,
    )

    assert stopped_after == ["intake"]
    lines = (tmp_path / "ws" / "stage_runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stage_executor_controller.py::test_resume_mvp_workflow_passes_controller -v`
Expected: FAIL — `resume_mvp_workflow() got an unexpected keyword argument 'controller'`.

- [ ] **Step 3: Add the controller parameter to both entrypoints**

In `src/mcm_agent/workflows/mvp.py`, add `controller` to `run_mvp_workflow` and `resume_mvp_workflow`. For `run_mvp_workflow`, change its signature and the `run_until_complete` call:

```python
def run_mvp_workflow(
    workspace_root: Path,
    inputs: TaskInput,
    *,
    providers: ProviderBundle | None = None,
    settings: Settings | None = None,
    supervisor_skills_dir: Path | None = None,
    auto_approve: bool = False,
    controller: "Callable[[object], str] | None" = None,
) -> None:
    workspace = create_workspace(workspace_root)
    provider_bundle = providers or _default_demo_providers()
    runtime_settings = settings or Settings()
    executor = StageExecutor(
        workspace.root,
        handlers=_mvp_stage_handlers(
            inputs,
            provider_bundle,
            settings=runtime_settings,
            supervisor_skills_dir=supervisor_skills_dir,
            auto_approve=auto_approve,
        ),
    )
    executor.run_until_complete(
        "intake", terminal_stage="submission_packager", controller=controller
    )
    if auto_approve:
        _approve_pending_checkpoints(workspace.root)
    _write_ai_use_report(workspace.root)
```

For `resume_mvp_workflow`, add the same parameter and pass it through:

```python
def resume_mvp_workflow(
    workspace_root: Path,
    inputs: TaskInput,
    *,
    providers: ProviderBundle | None = None,
    settings: Settings | None = None,
    supervisor_skills_dir: Path | None = None,
    auto_approve: bool = False,
    from_stage: str | None = None,
    until_stage: str | None = None,
    controller: "Callable[[object], str] | None" = None,
) -> None:
    workspace = create_workspace(workspace_root)
    provider_bundle = providers or _default_demo_providers()
    runtime_settings = settings or Settings()
    start_stage = from_stage or _resume_stage_from_state(workspace.root)
    executor = StageExecutor(
        workspace.root,
        handlers=_mvp_stage_handlers(
            inputs,
            provider_bundle,
            settings=runtime_settings,
            supervisor_skills_dir=supervisor_skills_dir,
            auto_approve=auto_approve,
        ),
    )
    executor.run_until_complete(
        start_stage,
        terminal_stage=until_stage or "submission_packager",
        controller=controller,
    )
    if auto_approve:
        _approve_pending_checkpoints(workspace.root)
    _write_ai_use_report(workspace.root)
```

Add the typing import at the top of `mvp.py` (next to the other `from __future__` / imports):

```python
from collections.abc import Callable
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stage_executor_controller.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/workflows/mvp.py tests/test_stage_executor_controller.py
git commit -m "feat: pass control hook through workflow entrypoints"
```

---

## Task 3: RunRegistry (threaded run, stop flag, pause checkpoint, log buffer)

**Files:**
- Create: `src/mcm_agent/server/run_registry.py`
- Test: `tests/test_run_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_registry.py
import time
from datetime import UTC, datetime

from mcm_agent.core.stage_executor import StageRunRecord
from mcm_agent.core.workspace import create_workspace
from mcm_agent.server.run_registry import RunRegistry
from mcm_agent.utils.json_io import read_json


def _record(stage_id, next_stage):
    now = datetime.now(UTC)
    return StageRunRecord(
        stage_id=stage_id, status="passed", started_at=now, finished_at=now,
        next_stage=next_stage,
    )


def _wait(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_registry_runs_to_completion(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    registry = RunRegistry()

    def run_fn(controller):
        for stage, nxt in [("intake", "problem_understanding"), ("problem_understanding", None)]:
            if controller(_record(stage, nxt)) != "continue":
                return

    registry.start(root.name, root, run_fn=run_fn, auto_approve=True, pause_after=set())
    assert _wait(lambda: registry.get(root.name).status == "done")


def test_registry_pauses_and_creates_pending_checkpoint(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    registry = RunRegistry()

    def run_fn(controller):
        for stage, nxt in [("intake", "problem_understanding"), ("problem_understanding", "modeling_council")]:
            if controller(_record(stage, nxt)) != "continue":
                return

    registry.start(
        root.name, root, run_fn=run_fn, auto_approve=False,
        pause_after={"problem_understanding"},
    )
    assert _wait(lambda: registry.get(root.name).status == "paused")
    handle = registry.get(root.name)
    assert handle.resume_from == "modeling_council"
    assert handle.pending_checkpoint_id is not None
    state = read_json(root / "task_state.json", {})
    pending = [c for c in state.get("checkpoints", []) if c["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["checkpoint_id"] == handle.pending_checkpoint_id


def test_registry_stop_flag_halts_run(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    registry = RunRegistry()
    started = {"v": False}

    def run_fn(controller):
        for i in range(100):
            started["v"] = True
            if controller(_record(f"stage_{i}", f"stage_{i + 1}")) != "continue":
                return
            time.sleep(0.02)

    registry.start(root.name, root, run_fn=run_fn, auto_approve=True, pause_after=set())
    assert _wait(lambda: started["v"])
    registry.stop(root.name)
    assert _wait(lambda: registry.get(root.name).status == "stopped")


def test_registry_rejects_concurrent_run(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    registry = RunRegistry()

    def run_fn(controller):
        time.sleep(0.3)

    registry.start(root.name, root, run_fn=run_fn, auto_approve=True, pause_after=set())
    try:
        registry.start(root.name, root, run_fn=run_fn, auto_approve=True, pause_after=set())
        raised = False
    except RunRegistry.AlreadyRunningError:
        raised = True
    assert raised
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcm_agent.server.run_registry'`.

- [ ] **Step 3: Implement the registry**

```python
# src/mcm_agent/server/run_registry.py
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
    ) -> RunHandle:
        with self._lock:
            if self.is_running(workspace_id):
                raise self.AlreadyRunningError(workspace_id)
            handle = RunHandle(workspace_id=workspace_id, workspace_root=workspace_root)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_registry.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/server/run_registry.py tests/test_run_registry.py
git commit -m "feat: add threaded workflow run registry with pause and stop"
```

---

## Task 4: Run / resume / run-status endpoints

**Files:**
- Create: `src/mcm_agent/server/routes_workflow.py`
- Modify: `src/mcm_agent/server/app.py`
- Test: `tests/test_server_workflow_control.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_workflow_control.py
import time

from fastapi.testclient import TestClient

from mcm_agent.server.app import create_app


def _client(tmp_path):
    return TestClient(create_app(workspace_base=tmp_path / "workspaces"))


def _seed_workspace(client):
    client.post("/api/workspaces", json={"workspace_id": "task_001"})
    client.post(
        "/api/workspaces/task_001/files",
        files={"files": ("problem.md", b"# Problem\nEvaluate three options.", "text/markdown")},
        data={"kind": "problem"},
    )


def _wait_run_state(client, expected, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = client.get("/api/workspaces/task_001/run").json()["state"]
        if state == expected:
            return True
        time.sleep(0.1)
    return False


def test_run_endpoint_runs_bounded_demo_to_completion(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)

    run = client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "problem_understanding"},
    )
    assert run.status_code == 200
    assert _wait_run_state(client, "done")

    lines = (tmp_path / "workspaces" / "task_001" / "stage_runs.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    stage_ids = [line for line in lines if "problem_understanding" in line]
    assert stage_ids  # reached problem_understanding


def test_run_endpoint_rejects_double_start(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)
    client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "submission_packager"},
    )
    second = client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True},
    )
    assert second.status_code == 409


def test_run_endpoint_requires_problem_file(tmp_path):
    client = _client(tmp_path)
    client.post("/api/workspaces", json={"workspace_id": "task_001"})
    resp = client.post("/api/workspaces/task_001/run", json={"demo": True, "auto_approve": True})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server_workflow_control.py -v`
Expected: FAIL — 404 on `/run` (route not registered yet).

- [ ] **Step 3: Implement the router and the run-fn builder**

```python
# src/mcm_agent/server/routes_workflow.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from mcm_agent.config import load_settings
from mcm_agent.core.models import TaskInput
from mcm_agent.server.routes_workspace import _workspace_root
from mcm_agent.server.run_registry import RunFn, RunRegistry
from mcm_agent.utils.json_io import read_json

PAUSE_AFTER_DEFAULT = {"user_discussion"}


def create_workflow_router(
    workspace_base: Path, registry: RunRegistry, config_path: Path
) -> APIRouter:
    router = APIRouter(prefix="/api/workspaces", tags=["workflow"])

    @router.post("/{workspace_id}/run")
    def run(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        run_fn = _build_run_fn(
            root,
            config_path,
            demo=bool(payload.get("demo")),
            auto_approve=bool(payload.get("auto_approve")),
            from_stage=payload.get("from_stage") or "intake",
            until_stage=payload.get("until_stage") or "submission_packager",
        )
        return _start(registry, root, run_fn, bool(payload.get("auto_approve")))

    @router.post("/{workspace_id}/resume")
    def resume(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        run_fn = _build_run_fn(
            root,
            config_path,
            demo=bool(payload.get("demo")),
            auto_approve=bool(payload.get("auto_approve")),
            from_stage=payload.get("from_stage"),
            until_stage=payload.get("until_stage") or "submission_packager",
        )
        return _start(registry, root, run_fn, bool(payload.get("auto_approve")))

    @router.post("/{workspace_id}/stop")
    def stop(workspace_id: str) -> dict[str, Any]:
        _workspace_root(workspace_base, workspace_id)
        registry.stop(workspace_id)
        return {"workspace_id": workspace_id, "stopping": True}

    @router.get("/{workspace_id}/run")
    def run_status(workspace_id: str) -> dict[str, Any]:
        _workspace_root(workspace_base, workspace_id)
        handle = registry.get(workspace_id)
        if handle is None:
            return {"workspace_id": workspace_id, "state": "idle"}
        return {
            "workspace_id": workspace_id,
            "state": handle.status,
            "duration_s": handle.duration_seconds(),
            "pending_checkpoint_id": handle.pending_checkpoint_id,
            "resume_from": handle.resume_from,
            "error": handle.error,
        }

    return router


def _start(
    registry: RunRegistry, root: Path, run_fn: RunFn, auto_approve: bool
) -> dict[str, Any]:
    try:
        handle = registry.start(
            root.name, root, run_fn=run_fn, auto_approve=auto_approve,
            pause_after=set() if auto_approve else PAUSE_AFTER_DEFAULT,
        )
    except RunRegistry.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail="run already in progress") from exc
    return {"workspace_id": root.name, "state": handle.status}


def _build_run_fn(
    root: Path,
    config_path: Path,
    *,
    demo: bool,
    auto_approve: bool,
    from_stage: str | None,
    until_stage: str,
) -> RunFn:
    inputs = _task_input_from_workspace(root)
    settings = load_settings(config_file=str(config_path)) if config_path.exists() else None

    def run_fn(controller) -> None:
        from mcm_agent.providers.factory import build_provider_bundle
        from mcm_agent.workflows.mvp import resume_mvp_workflow

        providers = None
        if not demo and settings is not None:
            providers = build_provider_bundle(settings, workspace_root=root)
        resume_mvp_workflow(
            root,
            inputs,
            providers=providers,
            settings=settings,
            auto_approve=auto_approve,
            from_stage=from_stage,
            until_stage=until_stage,
            controller=controller,
        )

    return run_fn


def _task_input_from_workspace(root: Path) -> TaskInput:
    problem_dir = root / "input" / "problem"
    problem_files = sorted(p for p in problem_dir.glob("*") if p.is_file()) if problem_dir.exists() else []
    if not problem_files:
        raise HTTPException(status_code=400, detail="no problem file uploaded")
    attach_dir = root / "input" / "attachments"
    attachments = sorted(p for p in attach_dir.glob("*") if p.is_file()) if attach_dir.exists() else []
    return TaskInput(problem_file=problem_files[0], attachments=attachments)
```

Then register it in `src/mcm_agent/server/app.py`. Add the imports and build a registry inside `create_app`:

```python
from mcm_agent.server.routes_workflow import create_workflow_router
from mcm_agent.server.run_registry import RunRegistry
```

Inside `create_app`, after the existing `app.include_router(create_artifact_router(...))` line, add:

```python
    app.state.run_registry = RunRegistry()
    app.include_router(
        create_workflow_router(
            app.state.workspace_base,
            app.state.run_registry,
            app.state.config_path,
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server_workflow_control.py -v`
Expected: PASS (3 passed). If the bounded demo run is slow, it still completes well under the 30s poll budget.

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/server/routes_workflow.py src/mcm_agent/server/app.py tests/test_server_workflow_control.py
git commit -m "feat: add run/resume/stop/run-status workflow endpoints"
```

---

## Task 5: Checkpoint approve + internal resume

**Files:**
- Modify: `src/mcm_agent/server/routes_workflow.py`
- Test: `tests/test_server_workflow_control.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server_workflow_control.py`:

```python
def test_pause_then_approve_resumes(tmp_path, monkeypatch):
    # Force a pause after "intake" so the bounded demo run pauses deterministically.
    import mcm_agent.server.routes_workflow as rw
    monkeypatch.setattr(rw, "PAUSE_AFTER_DEFAULT", {"intake"})

    client = _client(tmp_path)
    _seed_workspace(client)

    run = client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": False, "until_stage": "problem_understanding"},
    )
    assert run.status_code == 200
    assert _wait_run_state(client, "paused")

    status = client.get("/api/workspaces/task_001/run").json()
    checkpoint_id = status["pending_checkpoint_id"]
    assert checkpoint_id is not None

    approve = client.post(
        f"/api/workspaces/task_001/checkpoints/{checkpoint_id}/approve",
        json={"user_message": "looks good"},
    )
    assert approve.status_code == 200
    assert _wait_run_state(client, "done")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server_workflow_control.py::test_pause_then_approve_resumes -v`
Expected: FAIL — 404 on the `/approve` route.

- [ ] **Step 3: Implement approve + resume**

Add to `create_workflow_router` in `routes_workflow.py` (before `return router`):

```python
    @router.post("/{workspace_id}/checkpoints/{checkpoint_id}/approve")
    def approve(workspace_id: str, checkpoint_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        handle = registry.get(workspace_id)
        if handle is None or handle.status != "paused":
            raise HTTPException(status_code=409, detail="no paused run to approve")
        resume_from = handle.resume_from or "intake"

        from mcm_agent.core.coordinator import Coordinator

        try:
            Coordinator(root).approve_checkpoint(
                checkpoint_id, user_message=str(payload.get("user_message", ""))
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="checkpoint not found") from exc

        auto_approve = bool(payload.get("auto_approve"))
        run_fn = _build_run_fn(
            root,
            config_path,
            demo=bool(payload.get("demo", True)),
            auto_approve=auto_approve,
            from_stage=resume_from,
            until_stage=payload.get("until_stage") or "submission_packager",
        )
        return _start(registry, root, run_fn, auto_approve)
```

Note: `registry.start` replaces the prior (paused, non-running) handle for this workspace, which is the desired behaviour — the new thread resumes from `resume_from`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server_workflow_control.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/server/routes_workflow.py tests/test_server_workflow_control.py
git commit -m "feat: add checkpoint approve with internal resume"
```

---

## Task 6: SSE events + logs endpoints

**Files:**
- Modify: `src/mcm_agent/server/routes_workflow.py`
- Test: `tests/test_server_workflow_control.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server_workflow_control.py`:

```python
def test_events_stream_replays_after_completion(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)
    client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "problem_understanding"},
    )
    assert _wait_run_state(client, "done")

    # After completion, a fresh SSE connection replays stage events from file and closes.
    event_types = []
    with client.stream("GET", "/api/workspaces/task_001/events") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event:"):
                event_types.append(line.split(":", 1)[1].strip())
            if "run_finished" in line:
                break

    assert "stage_completed" in event_types
    assert "run_finished" in event_types


def test_logs_endpoint_returns_recent_lines(tmp_path):
    client = _client(tmp_path)
    _seed_workspace(client)
    client.post(
        "/api/workspaces/task_001/run",
        json={"demo": True, "auto_approve": True, "until_stage": "problem_understanding"},
    )
    assert _wait_run_state(client, "done")
    logs = client.get("/api/workspaces/task_001/logs").json()
    assert "stages" in logs
    assert any(s["stage_id"] == "problem_understanding" for s in logs["stages"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server_workflow_control.py::test_events_stream_replays_after_completion -v`
Expected: FAIL — 404 on `/events`.

- [ ] **Step 3: Implement events (SSE) and logs**

Add these imports at the top of `routes_workflow.py`:

```python
import json
import time

from fastapi.responses import StreamingResponse
```

Add inside `create_workflow_router` (before `return router`):

```python
    @router.get("/{workspace_id}/logs")
    def logs(workspace_id: str) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        return {"workspace_id": workspace_id, "stages": _read_stage_records(root)}

    @router.get("/{workspace_id}/events")
    def events(workspace_id: str) -> StreamingResponse:
        root = _workspace_root(workspace_base, workspace_id)
        return StreamingResponse(
            _event_stream(root, workspace_id, registry),
            media_type="text/event-stream",
        )

    return router


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _read_stage_records(root: Path) -> list[dict[str, Any]]:
    path = root / "stage_runs.jsonl"
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _event_stream(root: Path, workspace_id: str, registry: RunRegistry):
    emitted = 0
    last_state: str | None = None
    deadline = time.monotonic() + 900
    while True:
        records = _read_stage_records(root)
        for record in records[emitted:]:
            yield _sse("stage_completed", record)
        emitted = len(records)

        handle = registry.get(workspace_id)
        if handle is not None:
            for entry in handle.drain_logs():
                yield _sse("log", entry)
        state = handle.status if handle is not None else _state_from_files(root)
        if state != last_state:
            yield _sse("status", {"state": state})
            last_state = state

        if state == "paused" and handle is not None:
            yield _sse(
                "checkpoint_pending",
                {"checkpoint_id": handle.pending_checkpoint_id, "resume_from": handle.resume_from},
            )
            break
        if state in {"done", "failed", "stopped"}:
            yield _sse("run_finished", {"state": state})
            break
        if time.monotonic() > deadline:
            break
        time.sleep(0.2)


def _state_from_files(root: Path) -> str:
    state = read_json(root / "task_state.json", {})
    if isinstance(state, dict) and state.get("blocked_reason"):
        return "failed"
    manifest = root / "final_submission" / "submission_manifest.json"
    return "done" if manifest.exists() else "idle"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server_workflow_control.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/server/routes_workflow.py tests/test_server_workflow_control.py
git commit -m "feat: add SSE events and logs endpoints for workflow runs"
```

---

## Task 7: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the targeted server + executor suites**

Run: `python -m pytest tests/test_stage_executor_controller.py tests/test_run_registry.py tests/test_server_workflow_control.py tests/test_server_workspace.py tests/test_server_config.py -v`
Expected: all PASS.

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: all prior tests still pass plus the new ones (≈ 276 + 13 new). No regressions.

- [ ] **Step 3: Lint (if ruff is installed)**

Run: `ruff check src tests`
Expected: All checks passed. Fix any issues ruff reports in the new files (unused imports, etc.).

- [ ] **Step 4: Manual smoke (optional, not in CI)**

```bash
mcm-agent gui --host 127.0.0.1 --port 8787 &
curl -s -X POST localhost:8787/api/workspaces -H 'content-type: application/json' -d '{"workspace_id":"smoke"}'
# upload a problem file, then:
curl -s -X POST localhost:8787/api/workspaces/smoke/run -H 'content-type: application/json' \
  -d '{"demo":true,"auto_approve":true,"until_stage":"problem_understanding"}'
curl -s localhost:8787/api/workspaces/smoke/run   # -> {"state":"done", ...}
```

- [ ] **Step 5: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint fixes for workflow control api"
```

---

## Self-Review notes (spec coverage)

- §4.2 run registry + endpoints → Tasks 3, 4, 5, 6.
- §4.3 executor control hook → Task 1 (+ threaded through in Task 2).
- §4.4 thread execution model → Task 3 (`threading.Thread`, daemon).
- §4.5 SSE from `stage_runs.jsonl` + `task_state.json` + log buffer → Task 6.
- §7 run lifecycle (run → events → pause → approve → resume; stop) → Tasks 4, 5, 6 + registry tests in Task 3.
- §8 SSE event types (`status`, `stage_completed`, `log`, `checkpoint_pending`, `run_finished`) → Task 6. (`stage_started` and `gate` are deferred; `stage_completed` already carries gate routing via `next_stage`. If `gate` events are wanted, emit one when a record's stage_id is a gate — add in a later iteration.)
- §9 error handling: failed run → `status="failed"` + `error` (Task 3); 409 concurrent (Task 4); cooperative stop (Task 3); blocked gate surfaces via `_state_from_files`.
- §10 testing: unit (executor hook, registry) + integration (HTTP) with fake/demo providers; no JS tests (no frontend in this phase).

**Known follow-ups (carried to Phase 2+ or noted in spec §13):**
- Wiring real `Coordinator` checkpoint events to `PAUSE_AFTER_DEFAULT` stages so pauses reflect genuine human-decision points (currently pause is driven by a stage-name set; `user_discussion` is the default pause stage).
- Per-stage-internal heartbeat logs (agents don't yet emit fine-grained logs; only stage-boundary events stream today).
- `stage_started` and dedicated `gate` SSE events if the frontend needs them.
