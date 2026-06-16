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


def test_display_status_reports_stopping(tmp_path):
    from mcm_agent.server.run_registry import RunHandle

    root = create_workspace(tmp_path / "ws").root
    handle = RunHandle(workspace_id="w", workspace_root=root)
    handle.status = "running"
    assert handle.display_status() == "running"
    handle.stop_event.set()
    assert handle.display_status() == "stopping"


def test_registry_marks_failed_on_exception(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    registry = RunRegistry()

    def run_fn(controller):
        raise RuntimeError("boom")

    registry.start(root.name, root, run_fn=run_fn, auto_approve=True, pause_after=set())
    assert _wait(lambda: registry.get(root.name).status == "failed")
    assert "boom" in (registry.get(root.name).error or "")
