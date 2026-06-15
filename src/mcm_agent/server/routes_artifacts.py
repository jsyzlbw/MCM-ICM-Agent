from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


def create_artifact_router(workspace_base: Path) -> APIRouter:
    router = APIRouter(prefix="/api/workspaces/{workspace_id}/artifacts", tags=["artifacts"])

    @router.get("")
    def list_artifacts(workspace_id: str) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        artifacts = [
            str(path.relative_to(root))
            for path in sorted(root.rglob("*"))
            if path.is_file() and not _is_hidden_or_cache(path, root)
        ]
        return {"workspace_id": workspace_id, "artifacts": artifacts}

    @router.get("/content")
    def read_artifact_content(workspace_id: str, path: str) -> dict[str, Any]:
        root = _workspace_root(workspace_base, workspace_id)
        target = _safe_child(root, path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail=f"artifact not found: {path}")
        return {
            "workspace_id": workspace_id,
            "path": path,
            "content": target.read_text(encoding="utf-8"),
        }

    @router.get("/download")
    def download_artifact(workspace_id: str, path: str) -> FileResponse:
        root = _workspace_root(workspace_base, workspace_id)
        target = _safe_child(root, path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail=f"artifact not found: {path}")
        return FileResponse(target)

    return router


def _workspace_root(workspace_base: Path, workspace_id: str) -> Path:
    if any(char in workspace_id for char in {"/", "\\", ":"}) or workspace_id in {".", ".."}:
        raise HTTPException(status_code=400, detail="workspace_id contains unsafe characters")
    root = (workspace_base / workspace_id).resolve()
    base = workspace_base.resolve()
    if root != base and base not in root.parents:
        raise HTTPException(status_code=400, detail="workspace path escapes workspace base")
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"workspace not found: {workspace_id}")
    return root


def _safe_child(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if target == root or root not in target.parents:
        raise HTTPException(status_code=400, detail="artifact path escapes workspace")
    return target


def _is_hidden_or_cache(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return any(part.startswith(".") or part in {"__pycache__", ".pytest_cache"} for part in parts)
