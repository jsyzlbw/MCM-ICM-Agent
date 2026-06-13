from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from mcm_agent.core.models import EventRecord
from mcm_agent.utils.json_io import append_jsonl


class EventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def append(self, event: EventRecord) -> None:
        append_jsonl(self.path, event.model_dump(mode="json"))

    def read_all(self) -> list[EventRecord]:
        events: list[EventRecord] = []
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                events.append(EventRecord.model_validate(payload))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(f"invalid JSONL at line {line_number}") from exc
        return events
