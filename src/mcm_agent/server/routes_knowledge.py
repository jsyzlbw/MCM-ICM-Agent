from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from mcm_agent.server.config_store import read_config

DEFAULT_EXTENSIONS = [".md", ".txt", ".pdf"]


def create_knowledge_router(knowledge_base_dir: Path, config_path: Path) -> APIRouter:
    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

    def _extensions() -> set[str]:
        cfg = read_config(config_path)
        rag = cfg.get("rag", {}) if isinstance(cfg, dict) else {}
        exts = rag.get("ingest_extensions") or DEFAULT_EXTENSIONS
        return {e if e.startswith(".") else f".{e}" for e in exts}

    @router.get("/files")
    def list_files() -> dict[str, Any]:
        base = knowledge_base_dir
        base.mkdir(parents=True, exist_ok=True)
        exts = _extensions()
        files: list[dict[str, Any]] = []
        for path in sorted(item for item in base.rglob("*") if item.is_file()):
            rel_parts = path.relative_to(base).parts
            if any(part.startswith(".") for part in rel_parts):
                continue  # skip hidden dirs/files (e.g. parse caches)
            ext = path.suffix.lower()
            files.append(
                {
                    "path": path.relative_to(base).as_posix(),
                    "size": path.stat().st_size,
                    "ext": ext,
                    "ingestible": ext in exts,
                }
            )
        return {
            "knowledge_base_dir": str(base),
            "extensions": sorted(exts),
            "files": files,
            "ingestible_count": sum(1 for f in files if f["ingestible"]),
        }

    @router.post("/files")
    async def upload_files(
        subdir: str = Form(""),
        files: list[UploadFile] = File(...),
    ) -> dict[str, Any]:
        target_dir = _safe_subdir(knowledge_base_dir, subdir)
        target_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for upload in files:
            name = Path(upload.filename or "upload.bin").name
            dest = target_dir / name
            dest.write_bytes(await upload.read())
            saved.append(dest.relative_to(knowledge_base_dir).as_posix())
        return {"saved": saved}

    @router.delete("/files")
    def delete_file(path: str) -> dict[str, Any]:
        target = _safe_child(knowledge_base_dir, path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail=f"file not found: {path}")
        target.unlink()
        return {"deleted": path}

    @router.get("/index-preview")
    def index_preview() -> dict[str, Any]:
        """Offline dry-run: ingest .md/.txt into a throwaway FTS store and report chunk counts.

        PDFs are reported as pending (real PDF ingestion needs MinerU and happens per-run).
        """
        from mcm_agent.agents.rag import MethodologyStore, ingest_knowledge_base

        base = knowledge_base_dir
        base.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory() as tmp:
            store = MethodologyStore(Path(tmp) / "preview.db")
            store.initialize()
            notes = ingest_knowledge_base(base, store, list(_extensions()), mineru_provider=None)
            with sqlite3.connect(store.db_path) as conn:
                total = conn.execute("SELECT count(*) FROM methodology_docs").fetchone()[0]
        return {"total_chunks": int(total), "notes": notes}

    return router


def _safe_subdir(base: Path, subdir: str) -> Path:
    subdir = (subdir or "").strip().strip("/")
    if not subdir:
        return base
    target = (base / subdir).resolve()
    base_resolved = base.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise HTTPException(status_code=400, detail="subdir escapes knowledge base")
    return target


def _safe_child(base: Path, relative_path: str) -> Path:
    target = (base / relative_path).resolve()
    base_resolved = base.resolve()
    if target == base_resolved or base_resolved not in target.parents:
        raise HTTPException(status_code=400, detail="path escapes knowledge base")
    return target
