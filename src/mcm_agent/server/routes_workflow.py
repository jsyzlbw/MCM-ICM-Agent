from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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
        until_stage = payload.get("until_stage") or "submission_packager"
        run_fn = _build_run_fn(
            root,
            config_path,
            demo=bool(payload.get("demo")),
            auto_approve=bool(payload.get("auto_approve")),
            from_stage=payload.get("from_stage") or "intake",
            until_stage=until_stage,
        )
        return _start(registry, root, run_fn, bool(payload.get("auto_approve")), until_stage=until_stage)

    @router.post("/{workspace_id}/resume")
    def resume(workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        until_stage = payload.get("until_stage") or "submission_packager"
        run_fn = _build_run_fn(
            root,
            config_path,
            demo=bool(payload.get("demo")),
            auto_approve=bool(payload.get("auto_approve")),
            from_stage=payload.get("from_stage"),
            until_stage=until_stage,
        )
        return _start(registry, root, run_fn, bool(payload.get("auto_approve")), until_stage=until_stage)

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

    @router.post("/{workspace_id}/checkpoints/{checkpoint_id}/approve")
    def approve(workspace_id: str, checkpoint_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        handle = registry.get(workspace_id)
        if handle is None or handle.status != "paused":
            raise HTTPException(status_code=409, detail="no paused run to approve")
        resume_from = handle.resume_from or "intake"
        until_stage = handle.until_stage or "submission_packager"

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
            until_stage=payload.get("until_stage") or until_stage,
        )
        return _start(registry, root, run_fn, auto_approve, until_stage=payload.get("until_stage") or until_stage)

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


def _start(
    registry: RunRegistry, root: Path, run_fn: RunFn, auto_approve: bool, until_stage: str | None = None
) -> dict[str, Any]:
    try:
        handle = registry.start(
            root.name, root, run_fn=run_fn, auto_approve=auto_approve,
            pause_after=set() if auto_approve else PAUSE_AFTER_DEFAULT,
            until_stage=until_stage,
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

