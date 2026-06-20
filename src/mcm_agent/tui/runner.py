from __future__ import annotations

import threading
from typing import Callable, TypeVar

from rich.console import Console

from mcm_agent.tui.theme import ACCENT

T = TypeVar("T")


def run_with_spinner(fn: Callable[[], T], verb: str, *, console: Console | None = None) -> T:
    """Run a blocking callable in a worker thread while showing a one-line spinner
    ('∑ <verb>… (esc 中断)'). Returns fn()'s result; re-raises its exception."""
    console = console or Console()
    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - propagate to caller
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    # Use the hex accent inline (not the theme name) so it renders even with a
    # plain Console that has no MAG_THEME registered.
    with console.status(f"[{ACCENT}]∑[/] {verb}… (esc 中断)", spinner="dots"):
        thread.start()
        thread.join()
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["result"]  # type: ignore[return-value]
