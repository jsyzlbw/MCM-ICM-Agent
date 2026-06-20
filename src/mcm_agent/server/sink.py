"""EventSink abstraction layer (S2).

Provides the interface the future kernel uses instead of touching the terminal
directly.  Three concrete implementations ship here:

* ``DefaultSink``  — preserves today's terminal behaviour (print / input).
  Used in headless / test / in-process mode; no behaviour change from current.
* ``BusSink``      — bridges to S1's EventBus.  Publishes events via
  publish_threadsafe (safe to call from a worker thread).  ask() / permission()
  block synchronously until the client delivers an answer (or close() is called).

The ``EventSink`` Protocol defines the interface both share.
"""
from __future__ import annotations

import threading
from typing import Callable, Protocol, runtime_checkable

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

import asyncio


# ---------------------------------------------------------------------------
# Protocol / interface
# ---------------------------------------------------------------------------


@runtime_checkable
class EventSink(Protocol):
    """Interface the kernel uses for all user-facing I/O."""

    def output(self, text: str, markdown: bool = False) -> None:
        """Emit a general output text line."""
        ...

    def ask(self, prompt: str) -> str:
        """Prompt the user for text input; blocks until answer arrives."""
        ...

    def permission(self, summary: str, detail: str = "") -> bool:
        """Ask for approval; blocks until decision arrives.  Returns True=allow."""
        ...

    def step(
        self,
        step: int,
        stage_id: str,
        label: str,
        finished: bool = False,
    ) -> None:
        """Emit a step.started or step.finished event."""
        ...

    def progress(self, label: str) -> None:
        """Emit a stage.progress spinner update."""
        ...

    def artifact(self, kind: str, path: str) -> None:
        """Emit an artifact event (paper, pdf, data, …)."""
        ...

    def error(self, reason: str) -> None:
        """Emit an error event."""
        ...

    def done(self) -> None:
        """Emit a done event (one interaction round is complete)."""
        ...


# ---------------------------------------------------------------------------
# DefaultSink — terminal behaviour (print / input)
# ---------------------------------------------------------------------------


class DefaultSink:
    """Preserves today's terminal behaviour.

    Parameters
    ----------
    printer:
        Callable used for output (defaults to ``print``).
    inputter:
        Callable used for ask prompts (defaults to ``input``).
    auto_approve:
        Whether ``permission()`` auto-returns True without asking
        (matches current ``auto_approve`` behaviour; default True).
    """

    def __init__(
        self,
        printer: Callable[[str], None] | None = None,
        inputter: Callable[[str], str] | None = None,
        auto_approve: bool = True,
    ) -> None:
        self._print = printer if printer is not None else print
        self._input = inputter if inputter is not None else input
        self._auto_approve = auto_approve

    def output(self, text: str, markdown: bool = False) -> None:
        self._print(text)

    def ask(self, prompt: str) -> str:
        return self._input(prompt)

    def permission(self, summary: str, detail: str = "") -> bool:
        if self._auto_approve:
            return True
        answer = self._input(f"Allow: {summary}? [y/N] ")
        return answer.strip().lower() in ("y", "yes")

    def step(
        self,
        step: int,
        stage_id: str,
        label: str,
        finished: bool = False,
    ) -> None:
        status = "✓" if finished else "▶"
        self._print(f"{status} [{stage_id}:{step}] {label}")

    def progress(self, label: str) -> None:
        self._print(f"… {label}")

    def artifact(self, kind: str, path: str) -> None:
        self._print(f"artifact [{kind}] {path}")

    def error(self, reason: str) -> None:
        self._print(f"ERROR: {reason}")

    def done(self) -> None:
        pass  # no-op in terminal mode; prompt re-appears naturally


# ---------------------------------------------------------------------------
# BusSink — bridge to S1 EventBus
# ---------------------------------------------------------------------------

_TIMEOUT = 120.0  # seconds before a pending ask/permission is cancelled
_CLOSED_SENTINEL = object()  # delivered when close() is called


class BusSink:
    """Publishes events via EventBus; ask/permission block for a client reply.

    Parameters
    ----------
    bus:
        The EventBus instance (shared with the rest of the server).
    loop:
        The asyncio event loop the bus runs on.  Used with
        publish_threadsafe so the kernel can call us from any thread.
    """

    def __init__(self, bus: EventBus, loop: asyncio.AbstractEventLoop) -> None:
        self._bus = bus
        self._loop = loop
        self._counter = 0
        self._lock = threading.Lock()
        # Pending ask waiters: ask_id -> (threading.Event, container[str|sentinel])
        self._ask_waiters: dict[str, tuple[threading.Event, list]] = {}
        # Pending permission waiters: req_id -> (threading.Event, container[bool|sentinel])
        self._perm_waiters: dict[str, tuple[threading.Event, list]] = {}
        self._closed = False

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _next_id(self) -> str:
        with self._lock:
            self._counter += 1
            return str(self._counter)

    # ------------------------------------------------------------------
    # EventSink interface
    # ------------------------------------------------------------------

    def output(self, text: str, markdown: bool = False) -> None:
        self._bus.publish_threadsafe(
            OutputTextEvent(text=text, markdown=markdown), self._loop
        )

    def ask(self, prompt: str) -> str:
        """Publish AskRequestEvent and block until deliver_answer() is called."""
        ask_id = self._next_id()
        evt = threading.Event()
        container: list = []
        with self._lock:
            self._ask_waiters[ask_id] = (evt, container)
        self._bus.publish_threadsafe(
            AskRequestEvent(ask_id=ask_id, prompt=prompt), self._loop
        )
        evt.wait(timeout=_TIMEOUT)
        with self._lock:
            self._ask_waiters.pop(ask_id, None)
        if not container or container[0] is _CLOSED_SENTINEL:
            raise RuntimeError("BusSink closed or timed out while waiting for ask answer")
        return container[0]

    def permission(self, summary: str, detail: str = "") -> bool:
        """Publish PermissionRequestEvent and block until deliver_decision() is called."""
        req_id = self._next_id()
        evt = threading.Event()
        container: list = []
        with self._lock:
            self._perm_waiters[req_id] = (evt, container)
        self._bus.publish_threadsafe(
            PermissionRequestEvent(req_id=req_id, summary=summary, detail=detail),
            self._loop,
        )
        evt.wait(timeout=_TIMEOUT)
        with self._lock:
            self._perm_waiters.pop(req_id, None)
        if not container or container[0] is _CLOSED_SENTINEL:
            raise RuntimeError(
                "BusSink closed or timed out while waiting for permission decision"
            )
        return container[0]

    def step(
        self,
        step: int,
        stage_id: str,
        label: str,
        finished: bool = False,
    ) -> None:
        if finished:
            event = StepFinishedEvent(step=step, stage_id=stage_id, label=label)
        else:
            event = StepStartedEvent(step=step, stage_id=stage_id, label=label)
        self._bus.publish_threadsafe(event, self._loop)

    def progress(self, label: str) -> None:
        self._bus.publish_threadsafe(StageProgressEvent(label=label), self._loop)

    def artifact(self, kind: str, path: str) -> None:
        self._bus.publish_threadsafe(ArtifactEvent(kind=kind, path=path), self._loop)

    def error(self, reason: str) -> None:
        self._bus.publish_threadsafe(ErrorEvent(reason=reason), self._loop)

    def done(self) -> None:
        self._bus.publish_threadsafe(DoneEvent(), self._loop)

    # ------------------------------------------------------------------
    # Answer / decision delivery (called by the server's command router)
    # ------------------------------------------------------------------

    def deliver_answer(self, ask_id: str, answer: str) -> None:
        """Unblock a pending ask() call with the given answer."""
        with self._lock:
            waiter = self._ask_waiters.get(ask_id)
        if waiter is None:
            return  # already timed out or no such ask
        evt, container = waiter
        container.append(answer)
        evt.set()

    def deliver_decision(self, req_id: str, decision: str) -> None:
        """Unblock a pending permission() call.  decision='allow' → True."""
        with self._lock:
            waiter = self._perm_waiters.get(req_id)
        if waiter is None:
            return
        evt, container = waiter
        container.append(decision.lower() == "allow")
        evt.set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release all pending waiters so blocked threads don't deadlock."""
        self._closed = True
        with self._lock:
            ask_waiters = list(self._ask_waiters.values())
            perm_waiters = list(self._perm_waiters.values())
        for evt, container in ask_waiters:
            container.append(_CLOSED_SENTINEL)
            evt.set()
        for evt, container in perm_waiters:
            container.append(_CLOSED_SENTINEL)
            evt.set()
