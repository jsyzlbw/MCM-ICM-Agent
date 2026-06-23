"""Wire protocol pydantic models + JSON-RPC 2.0 codec for mag client/server.

AUTO-TRUTH: this file is the single source of truth for the mag wire protocol.
``scripts/gen_protocol_doc.py`` generates ``WIRE_PROTOCOL.md`` from these models.

Transport
---------
- TCP loopback 127.0.0.1:<port> (env MAG_HOST / MAG_PORT override).
- Each message is exactly one UTF-8 line terminated with ``\\n`` (NDJSON).
- Commands (client → server): JSON-RPC 2.0 request;  ``params.type`` routes.
- Events  (server → client): ``{"kind":"event","event":{"type":...,...}}`` envelope.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Union

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------

class _Base(BaseModel):
    """Shared config: forbid extra fields, allow population by name."""

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Command models  (client → server)
# Each has a ``type`` discriminator field that matches the JSON-RPC ``method``.
# ---------------------------------------------------------------------------

class PingCommand(_Base):
    """Health-check — server replies with a pong event."""

    type: Literal["core.ping"] = "core.ping"
    client: str


class SessionAttachCommand(_Base):
    """Establish or resume a session for the given workspace path."""

    type: Literal["session.attach"] = "session.attach"
    workspace: str


class InputSubmitCommand(_Base):
    """One line of user input (routed server-side by prefix: / ! @ or plain)."""

    type: Literal["input.submit"] = "input.submit"
    text: str


class AskAnswerCommand(_Base):
    """Response to an ``ask.request`` event."""

    type: Literal["ask.answer"] = "ask.answer"
    ask_id: str
    answer: str


class PermissionDecideCommand(_Base):
    """Response to a ``permission.request`` event (O7 human-audit gate)."""

    type: Literal["permission.decide"] = "permission.decide"
    req_id: str
    decision: str  # "allow" | "deny"


class InterruptCommand(_Base):
    """Interrupt the currently running stage (Esc)."""

    type: Literal["interrupt"] = "interrupt"


class ExitCommand(_Base):
    """Client is disconnecting cleanly."""

    type: Literal["exit"] = "exit"


# Union of all command types (used by decode_command)
_COMMAND_MAP: dict[str, type[_Base]] = {
    "core.ping": PingCommand,
    "session.attach": SessionAttachCommand,
    "input.submit": InputSubmitCommand,
    "ask.answer": AskAnswerCommand,
    "permission.decide": PermissionDecideCommand,
    "interrupt": InterruptCommand,
    "exit": ExitCommand,
}


# ---------------------------------------------------------------------------
# Event models  (server → client)
# Each has a ``type`` string constant.  Wrapped in the envelope by encode_event.
# ---------------------------------------------------------------------------

class StepStartedEvent(_Base):
    """A workflow step has begun."""

    type: Literal["step.started"] = "step.started"
    step: int
    stage_id: str
    label: str


class StepFinishedEvent(_Base):
    """A workflow step has completed."""

    type: Literal["step.finished"] = "step.finished"
    step: int
    stage_id: str
    label: str


class AssistantChunkEvent(_Base):
    """One streaming text chunk from the assistant (delta)."""

    type: Literal["assistant.chunk"] = "assistant.chunk"
    text: str


class AssistantTextEvent(_Base):
    """Complete (non-streaming) assistant message."""

    type: Literal["assistant.text"] = "assistant.text"
    text: str


class ToolCallEvent(_Base):
    """The assistant is calling a tool."""

    type: Literal["tool.call"] = "tool.call"
    name: str
    input: dict[str, Any]


class ToolResultEvent(_Base):
    """Result of a tool call."""

    type: Literal["tool.result"] = "tool.result"
    name: str
    exit_code: int
    output: str


class OutputTextEvent(_Base):
    """General output text from a command or notification."""

    type: Literal["output.text"] = "output.text"
    text: str
    markdown: bool = False


class AskRequestEvent(_Base):
    """Server needs user input — client should enter ask mode."""

    type: Literal["ask.request"] = "ask.request"
    ask_id: str
    prompt: str


class PermissionRequestEvent(_Base):
    """Server needs human approval (O7 gate)."""

    type: Literal["permission.request"] = "permission.request"
    req_id: str
    summary: str
    detail: str = ""


class StageProgressEvent(_Base):
    """Spinner / progress label update."""

    type: Literal["stage.progress"] = "stage.progress"
    label: str


class ArtifactEvent(_Base):
    """An output artifact has been produced."""

    type: Literal["artifact"] = "artifact"
    kind: str  # e.g. "paper", "pdf", "data"
    path: str


class ErrorEvent(_Base):
    """An error occurred; displayed in red."""

    type: Literal["error"] = "error"
    reason: str


class DoneEvent(_Base):
    """One interaction round is complete."""

    type: Literal["done"] = "done"


# Union of all event types (used by decode_event)
_EVENT_MAP: dict[str, type[_Base]] = {
    "step.started": StepStartedEvent,
    "step.finished": StepFinishedEvent,
    "assistant.chunk": AssistantChunkEvent,
    "assistant.text": AssistantTextEvent,
    "tool.call": ToolCallEvent,
    "tool.result": ToolResultEvent,
    "output.text": OutputTextEvent,
    "ask.request": AskRequestEvent,
    "permission.request": PermissionRequestEvent,
    "stage.progress": StageProgressEvent,
    "artifact": ArtifactEvent,
    "error": ErrorEvent,
    "done": DoneEvent,
}

# Type aliases for type hints
AnyCommand = Union[
    PingCommand,
    SessionAttachCommand,
    InputSubmitCommand,
    AskAnswerCommand,
    PermissionDecideCommand,
    InterruptCommand,
    ExitCommand,
]

AnyEvent = Union[
    StepStartedEvent,
    StepFinishedEvent,
    AssistantChunkEvent,
    AssistantTextEvent,
    ToolCallEvent,
    ToolResultEvent,
    OutputTextEvent,
    AskRequestEvent,
    PermissionRequestEvent,
    StageProgressEvent,
    ArtifactEvent,
    ErrorEvent,
    DoneEvent,
]


# ---------------------------------------------------------------------------
# Codec
# ---------------------------------------------------------------------------

def encode_command(cmd: _Base, id: int | str) -> str:
    """Encode a command as a JSON-RPC 2.0 request line (NDJSON, ends with \\n).

    Wire format::

        {"jsonrpc":"2.0","id":<id>,"method":<type>,"params":{<type>+fields}}\\n
    """
    params = cmd.model_dump()  # includes the "type" field
    method = params["type"]
    payload = {
        "jsonrpc": "2.0",
        "id": id,
        "method": method,
        "params": params,
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def decode_command(line: str) -> tuple[int | str, AnyCommand]:
    """Parse a JSON-RPC 2.0 request line → (id, command_model).

    Raises ``ValueError`` for unknown ``params.type``, ``json.JSONDecodeError``
    for invalid JSON, and ``pydantic.ValidationError`` for bad field types.
    """
    data = json.loads(line.strip())
    req_id = data["id"]
    params = data["params"]
    cmd_type = params["type"]
    cls = _COMMAND_MAP.get(cmd_type)
    if cls is None:
        raise ValueError(f"Unknown command type: {cmd_type!r}")
    return req_id, cls(**{k: v for k, v in params.items() if k != "type"})


def encode_event(event: _Base) -> str:
    """Encode an event as the envelope NDJSON line (ends with \\n).

    Wire format::

        {"kind":"event","event":{"type":<type>,...}}\\n
    """
    envelope = {"kind": "event", "event": event.model_dump()}
    return json.dumps(envelope, ensure_ascii=False) + "\n"


def decode_event(line: str) -> AnyEvent:
    """Parse an event envelope line → event model.

    Raises ``ValueError`` for unknown ``event.type``, ``json.JSONDecodeError``
    for invalid JSON, and ``pydantic.ValidationError`` for bad field types.
    """
    data = json.loads(line.strip())
    event_data = data["event"]
    ev_type = event_data["type"]
    cls = _EVENT_MAP.get(ev_type)
    if cls is None:
        raise ValueError(f"Unknown event type: {ev_type!r}")
    return cls(**{k: v for k, v in event_data.items() if k != "type"})
