from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mcm_agent.core.models import ArtifactRecord, ArtifactStatus
from mcm_agent.utils.json_io import read_json, write_json


class ArtifactRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not self.path.exists():
            write_json(self.path, [])

    def list(self) -> list[ArtifactRecord]:
        return [ArtifactRecord.model_validate(item) for item in read_json(self.path, [])]

    def get(self, artifact_id: str) -> ArtifactRecord:
        for record in self.list():
            if record.artifact_id == artifact_id:
                return record
        raise KeyError(f"artifact not found: {artifact_id}")

    def add(self, record: ArtifactRecord) -> None:
        records = self.list()
        if any(existing.artifact_id == record.artifact_id for existing in records):
            raise ValueError(f"artifact already exists: {record.artifact_id}")
        records.append(record)
        self._write(records)

    def update_status(self, artifact_id: str, status: ArtifactStatus) -> None:
        records = self.list()
        found = False
        for index, record in enumerate(records):
            if record.artifact_id == artifact_id:
                records[index] = record.model_copy(
                    update={"status": status, "updated_at": datetime.now(UTC)}
                )
                found = True
                break
        if not found:
            raise KeyError(f"artifact not found: {artifact_id}")
        self._write(records)

    def dependents_of(self, artifact_id: str) -> list[ArtifactRecord]:
        return [record for record in self.list() if artifact_id in record.depends_on]

    def mark_dependents_stale(self, artifact_id: str) -> list[str]:
        records = self.list()
        marked: list[str] = []
        for index, record in enumerate(records):
            if artifact_id in record.depends_on:
                records[index] = record.model_copy(
                    update={"status": ArtifactStatus.STALE, "updated_at": datetime.now(UTC)}
                )
                marked.append(record.artifact_id)
        self._write(records)
        return marked

    def _write(self, records: list[ArtifactRecord]) -> None:
        write_json(self.path, [record.model_dump(mode="json") for record in records])
