"""Tests for src/mcm_agent/server/event_bus.py — EventBus + EventWriter."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcm_agent.server.event_bus import EventBus, EventWriter
from mcm_agent.server.protocol import (
    AssistantChunkEvent,
    DoneEvent,
    ErrorEvent,
    OutputTextEvent,
)


# ---------------------------------------------------------------------------
# EventBus tests (driven via asyncio.run since pytest-asyncio not in project)
# ---------------------------------------------------------------------------

class TestEventBus:
    def test_single_subscriber_receives_event(self):
        async def run():
            bus = EventBus()
            q = bus.subscribe()
            ev = AssistantChunkEvent(text="hi")
            await bus.publish(ev)
            received = await asyncio.wait_for(q.get(), timeout=1.0)
            assert received is ev

        asyncio.run(run())

    def test_two_subscribers_both_receive(self):
        async def run():
            bus = EventBus()
            q1 = bus.subscribe()
            q2 = bus.subscribe()
            ev = DoneEvent()
            await bus.publish(ev)
            r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
            r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
            assert r1 is ev
            assert r2 is ev

        asyncio.run(run())

    def test_unsubscribe_stops_delivery(self):
        async def run():
            bus = EventBus()
            q1 = bus.subscribe()
            q2 = bus.subscribe()
            bus.unsubscribe(q2)
            ev = ErrorEvent(reason="oops")
            await bus.publish(ev)
            # q1 should receive
            r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
            assert r1 is ev
            # q2 should be empty
            assert q2.empty()

        asyncio.run(run())

    def test_multiple_events_ordered(self):
        async def run():
            bus = EventBus()
            q = bus.subscribe()
            events = [
                AssistantChunkEvent(text="a"),
                AssistantChunkEvent(text="b"),
                AssistantChunkEvent(text="c"),
            ]
            for ev in events:
                await bus.publish(ev)
            received = []
            for _ in events:
                received.append(await asyncio.wait_for(q.get(), timeout=1.0))
            assert [e.text for e in received] == ["a", "b", "c"]

        asyncio.run(run())

    def test_publish_threadsafe(self):
        """publish_threadsafe delivers to subscribers from a worker thread."""
        import threading

        async def run():
            bus = EventBus()
            q = bus.subscribe()
            loop = asyncio.get_event_loop()
            ev = OutputTextEvent(text="from thread")

            def worker():
                bus.publish_threadsafe(ev, loop)

            t = threading.Thread(target=worker)
            t.start()
            t.join()
            # give the loop a tick to process
            await asyncio.sleep(0.05)
            received = await asyncio.wait_for(q.get(), timeout=1.0)
            assert received is ev

        asyncio.run(run())


# ---------------------------------------------------------------------------
# EventWriter tests
# ---------------------------------------------------------------------------

class TestEventWriter:
    def test_write_and_read_single_event(self, tmp_path: Path):
        path = tmp_path / "events.jsonl"
        writer = EventWriter(path)
        ev = AssistantChunkEvent(text="hello")
        writer.write(ev)
        events = EventWriter.read_events(path)
        assert len(events) == 1
        assert isinstance(events[0], AssistantChunkEvent)
        assert events[0].text == "hello"

    def test_write_multiple_events(self, tmp_path: Path):
        path = tmp_path / "events.jsonl"
        writer = EventWriter(path)
        evs = [
            AssistantChunkEvent(text="a"),
            DoneEvent(),
            ErrorEvent(reason="boom"),
        ]
        for ev in evs:
            writer.write(ev)
        events = EventWriter.read_events(path)
        assert len(events) == 3
        assert isinstance(events[0], AssistantChunkEvent)
        assert isinstance(events[1], DoneEvent)
        assert isinstance(events[2], ErrorEvent)
        assert events[2].reason == "boom"

    def test_each_line_is_valid_ndjson(self, tmp_path: Path):
        path = tmp_path / "events.jsonl"
        writer = EventWriter(path)
        writer.write(DoneEvent())
        lines = path.read_text().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["kind"] == "event"
        assert data["event"]["type"] == "done"

    def test_appends_on_successive_writes(self, tmp_path: Path):
        path = tmp_path / "events.jsonl"
        w1 = EventWriter(path)
        w1.write(AssistantChunkEvent(text="first"))
        w2 = EventWriter(path)
        w2.write(AssistantChunkEvent(text="second"))
        events = EventWriter.read_events(path)
        assert len(events) == 2

    def test_read_events_empty_file(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        events = EventWriter.read_events(path)
        assert events == []

    def test_read_events_nonexistent_file(self, tmp_path: Path):
        path = tmp_path / "no_such.jsonl"
        events = EventWriter.read_events(path)
        assert events == []
