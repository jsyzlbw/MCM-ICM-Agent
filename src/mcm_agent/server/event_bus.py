"""asyncio pub/sub EventBus + NDJSON EventWriter for mag server.

EventBus
--------
- ``subscribe()`` → ``asyncio.Queue`` that receives every published event.
- ``unsubscribe(q)`` removes a subscriber queue.
- ``async publish(event)`` fans out to all subscriber queues.
- ``publish_threadsafe(event, loop)`` is safe to call from a worker thread;
  it uses ``loop.call_soon_threadsafe`` to schedule the fan-out on the loop.

EventWriter
-----------
- Appends each event as one NDJSON line to a ``.jsonl`` file (persistence /
  trace replay).
- ``write(event)`` — append one event.
- ``read_events(path)`` (classmethod) — read all lines back as event models.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcm_agent.server.protocol import AnyEvent, decode_event, encode_event


class EventBus:
    """asyncio pub/sub bus; thread-safe publish via publish_threadsafe."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Any]] = []

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[Any]:
        """Return a new subscriber queue that will receive all future events."""
        q: asyncio.Queue[Any] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Any]) -> None:
        """Remove a subscriber queue; future events will not be delivered."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass  # already removed

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: AnyEvent) -> None:
        """Fan-out *event* to every subscriber queue (must be called from the loop)."""
        for q in list(self._subscribers):
            await q.put(event)

    def publish_threadsafe(self, event: AnyEvent, loop: asyncio.AbstractEventLoop) -> None:
        """Schedule *event* publication from a worker thread.

        Uses ``loop.call_soon_threadsafe`` so the actual queue puts happen on
        the event loop thread — safe even when called from executor threads.
        """
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self.publish(event), loop=loop)
        )


class EventWriter:
    """Append events to a JSONL file; class-method to read them back."""

    def __init__(self, path: Path) -> None:
        self._path = path
        # Ensure the parent directory exists.
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, event: AnyEvent) -> None:
        """Append *event* as one NDJSON line (no trailing newline in the file itself)."""
        line = encode_event(event)  # already ends with \n
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)

    # ------------------------------------------------------------------
    # Read (class method — works without an instance)
    # ------------------------------------------------------------------

    @classmethod
    def read_events(cls, path: Path) -> list[AnyEvent]:
        """Return every event stored in *path*.

        Returns an empty list if the file does not exist or is empty.
        Skips blank lines silently.
        """
        if not path.exists():
            return []
        events: list[AnyEvent] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            events.append(decode_event(raw + "\n"))
        return events
