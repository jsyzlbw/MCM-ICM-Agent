from pathlib import Path
import json

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.session_store import SessionStore
from mcm_agent.core.workspace import create_workspace


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_session_store_appends_messages(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    store = SessionStore(workspace.root)

    store.append_message("user", "hello")
    store.append_message("assistant", "hi")

    rows = _jsonl(workspace.root / ".mag/chat/messages.jsonl")
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "hello"
    assert rows[1]["role"] == "assistant"


def test_session_store_appends_events(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    store = SessionStore(workspace.root)

    store.append_event("command.started", {"command": "help"})

    rows = _jsonl(workspace.root / ".mag/events.jsonl")
    assert rows[-1]["event_type"] == "command.started"
    assert rows[-1]["payload"] == {"command": "help"}


def test_session_store_read_recent_messages(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    store = SessionStore(workspace.root)
    for index in range(5):
        store.append_message("user", f"message {index}")

    recent = store.read_recent_messages(limit=2)

    assert [row["content"] for row in recent] == ["message 3", "message 4"]


def test_session_store_writes_summary_without_deleting_messages(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    store = SessionStore(workspace.root)
    store.append_message("user", "long discussion")

    store.write_summary("# Summary\n\nImportant context.")

    assert (workspace.root / ".mag/chat/summary.md").exists()
    assert _jsonl(workspace.root / ".mag/chat/messages.jsonl")


def test_interactive_session_records_command_and_reply(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)

    session.run_once("/help")

    messages = _jsonl(workspace.root / ".mag/chat/messages.jsonl")
    events = _jsonl(workspace.root / ".mag/events.jsonl")
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
    assert any(event["event_type"] == "command.started" for event in events)
    assert any(event["event_type"] == "command.finished" for event in events)
