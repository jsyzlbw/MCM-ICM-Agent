"""Tests for src/mcm_agent/server/sink.py (S2 EventSink layer).

Strategy
--------
* DefaultSink: purely synchronous; no asyncio needed.
* BusSink: needs a running asyncio loop.  Each test that exercises BusSink
  spins up a dedicated loop in a daemon thread, creates the BusSink bound to
  that loop, drives publish_threadsafe there, and collects events via a
  concurrent.futures.Future set from a subscriber callback.

All tests use short timeouts (2 s) so a bug fails fast rather than hanging.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any

import pytest

from mcm_agent.server.event_bus import EventBus
from mcm_agent.server.protocol import (
    ArtifactEvent,
    AskRequestEvent,
    DoneEvent,
    ErrorEvent,
    OutputTextEvent,
    PermissionRequestEvent,
    StageProgressEvent,
    StepFinishedEvent,
    StepStartedEvent,
)
from mcm_agent.server.sink import BusSink, DefaultSink, EventSink

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIMEOUT = 2.0  # seconds; fail fast in tests


def _make_loop_thread() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    """Start a dedicated asyncio loop in a daemon thread."""
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop, t


def _make_collector(
    bus: EventBus, loop: asyncio.AbstractEventLoop, n: int
) -> tuple[list[Any], concurrent.futures.Future]:
    """Subscribe to *bus* and return (collected_list, done_future).

    Subscribes synchronously (waits until the queue is registered) before
    returning, so the caller can publish immediately without a race.

    The done_future resolves (result = collected list) once *n* events land.
    """
    collected: list[Any] = []
    ready_event = threading.Event()
    done_future: concurrent.futures.Future = concurrent.futures.Future()

    async def _drain() -> None:
        q = bus.subscribe()
        # Signal that the queue is registered before we start waiting.
        ready_event.set()
        try:
            while len(collected) < n:
                event = await asyncio.wait_for(q.get(), timeout=_TIMEOUT)
                collected.append(event)
            # Signal completion back to the test thread via the thread-safe future.
            loop.call_soon_threadsafe(
                lambda: done_future.set_result(collected)
                if not done_future.done()
                else None
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                lambda e=exc: done_future.set_exception(e)
                if not done_future.done()
                else None
            )

    asyncio.run_coroutine_threadsafe(_drain(), loop)
    # Wait until the subscriber queue is actually registered before returning.
    ready_event.wait(timeout=_TIMEOUT)
    return collected, done_future


# ===========================================================================
# DefaultSink tests
# ===========================================================================


class TestDefaultSink:
    def test_output_routes_to_injected_printer(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.output("hello world")
        assert lines == ["hello world"]

    def test_output_markdown_flag_forwarded(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.output("**bold**", markdown=True)
        assert lines == ["**bold**"]

    def test_ask_routes_to_injected_inputter(self) -> None:
        sink = DefaultSink(inputter=lambda _: "my answer")
        assert sink.ask("Question?") == "my answer"

    def test_ask_passes_prompt_to_inputter(self) -> None:
        prompts: list[str] = []
        sink = DefaultSink(inputter=lambda p: (prompts.append(p) or "ok"))
        sink.ask("Enter name: ")
        assert prompts == ["Enter name: "]

    def test_permission_auto_approve_true_by_default(self) -> None:
        sink = DefaultSink()
        assert sink.permission("delete file") is True

    def test_permission_auto_approve_false_uses_inputter(self) -> None:
        sink = DefaultSink(inputter=lambda _: "y", auto_approve=False)
        assert sink.permission("do something") is True
        sink2 = DefaultSink(inputter=lambda _: "n", auto_approve=False)
        assert sink2.permission("do something") is False

    def test_step_started_prints(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.step(1, "s1", "Writing intro", finished=False)
        assert lines and "Writing intro" in lines[0]

    def test_step_finished_prints(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.step(2, "s2", "Proof done", finished=True)
        assert lines and "Proof done" in lines[0]

    def test_progress_prints(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.progress("Running solver…")
        assert lines and "Running solver" in lines[0]

    def test_artifact_prints(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.artifact("paper", "output/main.tex")
        assert lines and "output/main.tex" in lines[0]

    def test_error_prints(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.error("something went wrong")
        assert lines and "something went wrong" in lines[0]

    def test_done_is_noop(self) -> None:
        lines: list[str] = []
        sink = DefaultSink(printer=lines.append)
        sink.done()
        assert lines == []

    def test_default_sink_satisfies_protocol(self) -> None:
        sink = DefaultSink()
        assert isinstance(sink, EventSink)


# ===========================================================================
# BusSink tests
# ===========================================================================


class TestBusSink:
    @pytest.fixture()
    def bus_loop(self):
        """Yield (bus, sink, loop); stop the loop after the test."""
        loop, _ = _make_loop_thread()
        bus = EventBus()
        sink = BusSink(bus=bus, loop=loop)
        yield bus, sink, loop
        # Stop the loop after each test
        loop.call_soon_threadsafe(loop.stop)

    # -----------------------------------------------------------------------
    # output
    # -----------------------------------------------------------------------

    def test_output_publishes_output_text_event(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.output("test message")
        fut.result(timeout=_TIMEOUT)
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, OutputTextEvent)
        assert ev.text == "test message"
        assert ev.markdown is False

    def test_output_markdown_flag(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.output("**bold**", markdown=True)
        fut.result(timeout=_TIMEOUT)
        assert events[0].markdown is True

    # -----------------------------------------------------------------------
    # step / progress / artifact / error / done
    # -----------------------------------------------------------------------

    def test_step_started_publishes_event(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.step(1, "s1", "Intro", finished=False)
        fut.result(timeout=_TIMEOUT)
        assert isinstance(events[0], StepStartedEvent)
        assert events[0].label == "Intro"

    def test_step_finished_publishes_event(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.step(2, "s2", "Done", finished=True)
        fut.result(timeout=_TIMEOUT)
        assert isinstance(events[0], StepFinishedEvent)

    def test_progress_publishes_event(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.progress("crunching…")
        fut.result(timeout=_TIMEOUT)
        assert isinstance(events[0], StageProgressEvent)
        assert events[0].label == "crunching…"

    def test_artifact_publishes_event(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.artifact("pdf", "output/main.pdf")
        fut.result(timeout=_TIMEOUT)
        assert isinstance(events[0], ArtifactEvent)
        assert events[0].path == "output/main.pdf"

    def test_error_publishes_event(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.error("oops")
        fut.result(timeout=_TIMEOUT)
        assert isinstance(events[0], ErrorEvent)
        assert events[0].reason == "oops"

    def test_done_publishes_event(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        events, fut = _make_collector(bus, loop, 1)
        sink.done()
        fut.result(timeout=_TIMEOUT)
        assert isinstance(events[0], DoneEvent)

    # -----------------------------------------------------------------------
    # ask — round-trip
    # -----------------------------------------------------------------------

    def test_ask_publishes_ask_request_and_returns_answer(self, bus_loop) -> None:
        """
        Thread A calls sink.ask("Q?") — blocks.
        Test observes AskRequestEvent from bus, then delivers the answer.
        Thread A should unblock and return "my_answer".
        """
        bus, sink, loop = bus_loop
        received_events: list[Any] = []

        async def _sub() -> None:
            q = bus.subscribe()
            ev = await asyncio.wait_for(q.get(), timeout=_TIMEOUT)
            received_events.append(ev)

        fut = asyncio.run_coroutine_threadsafe(_sub(), loop)

        result_holder: list[str] = []
        exc_holder: list[BaseException] = []

        def _ask_thread() -> None:
            try:
                result_holder.append(sink.ask("Q?"))
            except Exception as e:
                exc_holder.append(e)

        t = threading.Thread(target=_ask_thread, daemon=True)
        t.start()

        # Wait for the AskRequestEvent to be published
        fut.result(timeout=_TIMEOUT)

        assert len(received_events) == 1
        ev = received_events[0]
        assert isinstance(ev, AskRequestEvent)
        assert ev.prompt == "Q?"
        ask_id = ev.ask_id

        # Deliver the answer
        sink.deliver_answer(ask_id, "my_answer")

        t.join(timeout=_TIMEOUT)
        assert not t.is_alive(), "ask() thread did not unblock"
        assert not exc_holder, f"ask() raised: {exc_holder}"
        assert result_holder == ["my_answer"]

    def test_ask_ids_are_unique(self, bus_loop) -> None:
        """Each ask() generates a distinct ask_id (monotonic counter)."""
        bus, sink, loop = bus_loop
        ids_seen: list[str] = []

        async def _gather_two() -> None:
            q = bus.subscribe()
            for _ in range(2):
                ev = await asyncio.wait_for(q.get(), timeout=_TIMEOUT)
                if isinstance(ev, AskRequestEvent):
                    ids_seen.append(ev.ask_id)

        fut = asyncio.run_coroutine_threadsafe(_gather_two(), loop)

        # Fire two asks in background threads; deliver answers immediately.
        def _do_ask(prompt: str) -> None:
            answer_box: list[str] = []

            async def _watch() -> None:
                q = bus.subscribe()
                ev = await asyncio.wait_for(q.get(), timeout=_TIMEOUT)
                if isinstance(ev, AskRequestEvent) and ev.prompt == prompt:
                    sink.deliver_answer(ev.ask_id, "ok")

            asyncio.run_coroutine_threadsafe(_watch(), loop)
            sink.ask(prompt)

        t1 = threading.Thread(target=_do_ask, args=("first",), daemon=True)
        t2 = threading.Thread(target=_do_ask, args=("second",), daemon=True)
        t1.start(); t2.start()
        t1.join(timeout=_TIMEOUT); t2.join(timeout=_TIMEOUT)

        # The two ask_ids seen by _gather_two should be distinct
        # (let it collect what it can; main assertion is no duplicate)
        try:
            fut.result(timeout=_TIMEOUT)
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
            pass
        assert len(set(ids_seen)) == len(ids_seen)

    # -----------------------------------------------------------------------
    # permission — round-trip
    # -----------------------------------------------------------------------

    def test_permission_allow(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        received_events: list[Any] = []

        async def _sub() -> None:
            q = bus.subscribe()
            ev = await asyncio.wait_for(q.get(), timeout=_TIMEOUT)
            received_events.append(ev)

        fut = asyncio.run_coroutine_threadsafe(_sub(), loop)

        result_holder: list[bool] = []

        def _perm_thread() -> None:
            result_holder.append(sink.permission("rm -rf /"))

        t = threading.Thread(target=_perm_thread, daemon=True)
        t.start()

        fut.result(timeout=_TIMEOUT)
        ev = received_events[0]
        assert isinstance(ev, PermissionRequestEvent)
        assert ev.summary == "rm -rf /"

        sink.deliver_decision(ev.req_id, "allow")
        t.join(timeout=_TIMEOUT)
        assert result_holder == [True]

    def test_permission_deny(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        received_events: list[Any] = []

        async def _sub() -> None:
            q = bus.subscribe()
            ev = await asyncio.wait_for(q.get(), timeout=_TIMEOUT)
            received_events.append(ev)

        fut = asyncio.run_coroutine_threadsafe(_sub(), loop)
        result_holder: list[bool] = []

        def _perm_thread() -> None:
            result_holder.append(sink.permission("drop table"))

        t = threading.Thread(target=_perm_thread, daemon=True)
        t.start()
        fut.result(timeout=_TIMEOUT)
        sink.deliver_decision(received_events[0].req_id, "deny")
        t.join(timeout=_TIMEOUT)
        assert result_holder == [False]

    # -----------------------------------------------------------------------
    # close() — release pending waiters
    # -----------------------------------------------------------------------

    def test_close_releases_pending_ask(self, bus_loop) -> None:
        """close() must unblock a thread blocked in ask() without deadlock."""
        bus, sink, loop = bus_loop
        exc_holder: list[BaseException] = []

        def _ask_thread() -> None:
            try:
                sink.ask("blocking prompt")
            except RuntimeError:
                pass  # expected: sink closed
            except Exception as e:
                exc_holder.append(e)

        t = threading.Thread(target=_ask_thread, daemon=True)
        t.start()

        # Give the ask() a moment to block
        time.sleep(0.05)
        sink.close()

        t.join(timeout=_TIMEOUT)
        assert not t.is_alive(), "close() did not release the blocked ask()"
        assert not exc_holder

    def test_close_releases_pending_permission(self, bus_loop) -> None:
        bus, sink, loop = bus_loop
        exc_holder: list[BaseException] = []

        def _perm_thread() -> None:
            try:
                sink.permission("dangerous op")
            except RuntimeError:
                pass
            except Exception as e:
                exc_holder.append(e)

        t = threading.Thread(target=_perm_thread, daemon=True)
        t.start()
        time.sleep(0.05)
        sink.close()
        t.join(timeout=_TIMEOUT)
        assert not t.is_alive(), "close() did not release the blocked permission()"
        assert not exc_holder

    def test_bus_sink_satisfies_protocol(self, bus_loop) -> None:
        _, sink, _ = bus_loop
        assert isinstance(sink, EventSink)
