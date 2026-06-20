"""Tests for src/mcm_agent/server/protocol.py — wire protocol round-trips."""
from __future__ import annotations

import json

import pytest

from mcm_agent.server.protocol import (
    # Commands
    PingCommand,
    SessionAttachCommand,
    InputSubmitCommand,
    AskAnswerCommand,
    PermissionDecideCommand,
    InterruptCommand,
    ExitCommand,
    # Events
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
    # Codec
    encode_command,
    decode_command,
    encode_event,
    decode_event,
)


# ---------------------------------------------------------------------------
# Command round-trips
# ---------------------------------------------------------------------------

class TestCommandEncodeDecodeRoundtrip:
    def test_ping_roundtrip(self):
        cmd = PingCommand(client="test-cli")
        line = encode_command(cmd, id=1)
        data = json.loads(line)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["method"] == "core.ping"
        assert data["params"]["client"] == "test-cli"
        assert data["params"]["type"] == "core.ping"
        assert line.endswith("\n")

        req_id, decoded = decode_command(line)
        assert req_id == 1
        assert isinstance(decoded, PingCommand)
        assert decoded.client == "test-cli"

    def test_session_attach_roundtrip(self):
        cmd = SessionAttachCommand(workspace="/tmp/ws")
        line = encode_command(cmd, id="abc-1")
        req_id, decoded = decode_command(line)
        assert req_id == "abc-1"
        assert isinstance(decoded, SessionAttachCommand)
        assert decoded.workspace == "/tmp/ws"

    def test_input_submit_roundtrip(self):
        cmd = InputSubmitCommand(text="hello world")
        line = encode_command(cmd, id=2)
        req_id, decoded = decode_command(line)
        assert req_id == 2
        assert isinstance(decoded, InputSubmitCommand)
        assert decoded.text == "hello world"

    def test_ask_answer_roundtrip(self):
        cmd = AskAnswerCommand(ask_id="ask-42", answer="yes")
        line = encode_command(cmd, id=3)
        req_id, decoded = decode_command(line)
        assert req_id == 3
        assert isinstance(decoded, AskAnswerCommand)
        assert decoded.ask_id == "ask-42"
        assert decoded.answer == "yes"

    def test_permission_decide_roundtrip(self):
        cmd = PermissionDecideCommand(req_id="perm-7", decision="allow")
        line = encode_command(cmd, id=4)
        req_id, decoded = decode_command(line)
        assert req_id == 4
        assert isinstance(decoded, PermissionDecideCommand)
        assert decoded.req_id == "perm-7"
        assert decoded.decision == "allow"

    def test_interrupt_roundtrip(self):
        cmd = InterruptCommand()
        line = encode_command(cmd, id=5)
        req_id, decoded = decode_command(line)
        assert req_id == 5
        assert isinstance(decoded, InterruptCommand)

    def test_exit_roundtrip(self):
        cmd = ExitCommand()
        line = encode_command(cmd, id=6)
        req_id, decoded = decode_command(line)
        assert req_id == 6
        assert isinstance(decoded, ExitCommand)


class TestDecodeCommandRoutingByType:
    """decode_command must route by params.type to correct model."""

    def test_routes_ping(self):
        line = json.dumps({
            "jsonrpc": "2.0", "id": 10, "method": "core.ping",
            "params": {"type": "core.ping", "client": "x"}
        }) + "\n"
        _, cmd = decode_command(line)
        assert isinstance(cmd, PingCommand)

    def test_routes_session_attach(self):
        line = json.dumps({
            "jsonrpc": "2.0", "id": 11, "method": "session.attach",
            "params": {"type": "session.attach", "workspace": "/ws"}
        }) + "\n"
        _, cmd = decode_command(line)
        assert isinstance(cmd, SessionAttachCommand)

    def test_routes_input_submit(self):
        line = json.dumps({
            "jsonrpc": "2.0", "id": 12, "method": "input.submit",
            "params": {"type": "input.submit", "text": "hi"}
        }) + "\n"
        _, cmd = decode_command(line)
        assert isinstance(cmd, InputSubmitCommand)

    def test_unknown_type_raises(self):
        line = json.dumps({
            "jsonrpc": "2.0", "id": 99, "method": "unknown.cmd",
            "params": {"type": "unknown.cmd"}
        }) + "\n"
        with pytest.raises((ValueError, KeyError, Exception)):
            decode_command(line)

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            decode_command("not json\n")


# ---------------------------------------------------------------------------
# Event round-trips
# ---------------------------------------------------------------------------

class TestEventEncodeDecodeRoundtrip:
    def test_step_started(self):
        ev = StepStartedEvent(step=1, stage_id="S1", label="Starting")
        line = encode_event(ev)
        data = json.loads(line)
        assert data["kind"] == "event"
        assert data["event"]["type"] == "step.started"
        assert line.endswith("\n")

        decoded = decode_event(line)
        assert isinstance(decoded, StepStartedEvent)
        assert decoded.step == 1
        assert decoded.stage_id == "S1"
        assert decoded.label == "Starting"

    def test_step_finished(self):
        ev = StepFinishedEvent(step=2, stage_id="S2", label="Done")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, StepFinishedEvent)
        assert decoded.step == 2

    def test_assistant_chunk(self):
        ev = AssistantChunkEvent(text="hello")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, AssistantChunkEvent)
        assert decoded.text == "hello"

    def test_assistant_text(self):
        ev = AssistantTextEvent(text="full answer")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, AssistantTextEvent)
        assert decoded.text == "full answer"

    def test_tool_call(self):
        ev = ToolCallEvent(name="bash", input={"cmd": "ls"})
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, ToolCallEvent)
        assert decoded.name == "bash"
        assert decoded.input == {"cmd": "ls"}

    def test_tool_result(self):
        ev = ToolResultEvent(name="bash", exit_code=0, output="file.txt")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, ToolResultEvent)
        assert decoded.exit_code == 0

    def test_output_text_defaults(self):
        ev = OutputTextEvent(text="[ok]")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, OutputTextEvent)
        assert decoded.markdown is False

    def test_output_text_markdown(self):
        ev = OutputTextEvent(text="**bold**", markdown=True)
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, OutputTextEvent)
        assert decoded.markdown is True

    def test_ask_request(self):
        ev = AskRequestEvent(ask_id="ask-1", prompt="Continue?")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, AskRequestEvent)
        assert decoded.ask_id == "ask-1"

    def test_permission_request_defaults(self):
        ev = PermissionRequestEvent(req_id="p-1", summary="Run shell?")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, PermissionRequestEvent)
        assert decoded.detail == ""

    def test_permission_request_with_detail(self):
        ev = PermissionRequestEvent(req_id="p-2", summary="Write file?", detail="path=/etc/hosts")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, PermissionRequestEvent)
        assert decoded.detail == "path=/etc/hosts"

    def test_stage_progress(self):
        ev = StageProgressEvent(label="Solving...")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, StageProgressEvent)
        assert decoded.label == "Solving..."

    def test_artifact(self):
        ev = ArtifactEvent(kind="paper", path="paper/main.tex")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, ArtifactEvent)
        assert decoded.kind == "paper"
        assert decoded.path == "paper/main.tex"

    def test_error(self):
        ev = ErrorEvent(reason="LLM timeout")
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, ErrorEvent)
        assert decoded.reason == "LLM timeout"

    def test_done(self):
        ev = DoneEvent()
        line = encode_event(ev)
        decoded = decode_event(line)
        assert isinstance(decoded, DoneEvent)

    def test_unknown_event_type_raises(self):
        line = json.dumps({"kind": "event", "event": {"type": "unknown.whatever"}}) + "\n"
        with pytest.raises(Exception):
            decode_event(line)

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            decode_event("bad json\n")
