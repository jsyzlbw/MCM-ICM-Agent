from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


UPLOAD_DIRS = {
    "problem": "input/problem",
    "attachment": "input/attachments",
    "template": "input/template",
    "chat": "input/chat_uploads",
}


def create_workspace_router(workspace_base: Path) -> APIRouter:
    router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

    @router.post("")
    def create_workspace_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        workspace_id = _workspace_id(payload.get("workspace_id"))
        workspace = create_workspace(workspace_base / workspace_id)
        return _workspace_summary(workspace.root)

    @router.get("")
    def list_workspaces() -> dict[str, Any]:
        workspace_base.mkdir(parents=True, exist_ok=True)
        workspaces = [
            _workspace_summary(path)
            for path in sorted(workspace_base.iterdir())
            if path.is_dir() and (path / "task_state.json").exists()
        ]
        return {"workspaces": workspaces}

    @router.get("/{workspace_id}")
    def get_workspace(workspace_id: str) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        return _workspace_summary(root)

    @router.post("/{workspace_id}/files")
    async def upload_files(
        workspace_id: str,
        kind: str = Form("attachment"),
        files: list[UploadFile] = File(...),
    ) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        relative_dir = UPLOAD_DIRS.get(kind)
        if relative_dir is None:
            raise HTTPException(status_code=400, detail=f"unknown upload kind: {kind}")
        target_dir = root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for upload in files:
            filename = Path(upload.filename or "upload.bin").name
            target = target_dir / filename
            target.write_bytes(await upload.read())
            saved.append(str(target.relative_to(root)))
        return {"workspace_id": workspace_id, "saved": saved}

    @router.get("/{workspace_id}/status")
    def workspace_status(workspace_id: str) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        state = read_json(root / "task_state.json", {})
        return {
            "workspace_id": workspace_id,
            "root": str(root),
            "state": state,
            "failed_gate": _latest_failed_gate(root),
            "recent_stages": _recent_stage_runs(root, limit=10),
        }

    return router


def _workspace_id(value: object) -> str:
    workspace_id = str(value or "").strip()
    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspace_id is required")
    if any(char in workspace_id for char in {"/", "\\", ":"}) or workspace_id in {".", ".."}:
        raise HTTPException(status_code=400, detail="workspace_id contains unsafe characters")
    return workspace_id


def _workspace_root(workspace_base: Path, workspace_id: str) -> Path:
    safe_id = _workspace_id(workspace_id)
    root = (workspace_base / safe_id).resolve()
    base = workspace_base.resolve()
    if root != base and base not in root.parents:
        raise HTTPException(status_code=400, detail="workspace path escapes workspace base")
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"workspace not found: {workspace_id}")
    return root


def _workspace_summary(root: Path) -> dict[str, Any]:
    state = read_json(root / "task_state.json", {})
    return {
        "workspace_id": root.name,
        "root": str(root),
        "state": state,
        "recent_stages": _recent_stage_runs(root, limit=5),
    }


def _latest_failed_gate(workspace_path: Path) -> dict[str, object] | None:
    for relative_path in [
        "review/final_gate.json",
        "review/figure_gate.json",
        "review/validation_gate.json",
        "review/source_gate.json",
        "review/extraction_gate.json",
    ]:
        payload = read_json(workspace_path / relative_path, {})
        if isinstance(payload, dict) and payload.get("status") == "fail":
            return payload
    return None


def _recent_stage_runs(workspace_path: Path, *, limit: int) -> list[dict[str, object]]:
    path = workspace_path / "stage_runs.jsonl"
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records[-limit:]
