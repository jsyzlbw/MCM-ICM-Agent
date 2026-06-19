from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from mcm_agent.core.redaction import redact_secrets
from mcm_agent.utils.json_io import append_jsonl


class SessionStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.chat_path = self.root / ".mag" / "chat" / "messages.jsonl"
        self.event_path = self.root / ".mag" / "events.jsonl"

    def append_message(self, role: Literal["user", "assistant", "system"], content: str) -> None:
        append_jsonl(
            self.chat_path,
            {
                "role": role,
                "content": redact_secrets(content),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    def append_event(self, event_type: str, payload: dict[str, object] | None = None) -> None:
        append_jsonl(
            self.event_path,
            {
                "event_type": event_type,
                "payload": payload or {},
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    def read_recent_messages(self, limit: int = 20) -> list[dict[str, object]]:
        if not self.chat_path.exists():
            return []
        import json

        rows = [
            json.loads(line)
            for line in self.chat_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return rows[-limit:]

    def write_summary(self, summary: str) -> None:
        path = self.root / ".mag" / "chat" / "summary.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary, encoding="utf-8")
