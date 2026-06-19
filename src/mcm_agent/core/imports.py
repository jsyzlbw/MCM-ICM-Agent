from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import hashlib
import shutil

from mcm_agent.core.workspace_models import ImportedResource
from mcm_agent.utils.json_io import append_jsonl


def copy_resource(
    source: Path,
    target_dir: Path,
    resource_type: str,
    metadata: dict[str, str] | None = None,
) -> ImportedResource:
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(str(source))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_target(source, target_dir)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)
    now = datetime.now(UTC)
    digest = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:10]
    return ImportedResource(
        resource_id=f"{resource_type}_{digest}",
        resource_type=resource_type,  # type: ignore[arg-type]
        source_path=str(source),
        workspace_path=str(target),
        created_at=now,
        metadata=metadata or {},
    )


def record_import(root: Path, resource: ImportedResource) -> None:
    append_jsonl(root / ".mag" / "resources.jsonl", resource.model_dump(mode="json"))


def _unique_target(source: Path, target_dir: Path) -> Path:
    candidate = target_dir / source.name
    if not candidate.exists():
        return candidate
    digest = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:8]
    if source.is_dir():
        return target_dir / f"{source.name}-{digest}"
    return target_dir / f"{source.stem}-{digest}{source.suffix}"
