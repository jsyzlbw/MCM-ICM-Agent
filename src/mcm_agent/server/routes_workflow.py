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
