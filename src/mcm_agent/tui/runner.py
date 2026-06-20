from __future__ import annotations

import contextlib
import select
import sys
import threading
from typing import Callable, TypeVar

from rich.console import Console

from mcm_agent.tui.theme import ACCENT

T = TypeVar("T")


class Interrupted(Exception):
    """User abandoned a long operation (Esc on a TTY, or Ctrl+C) while the spinner
    was active. The worker thread is a daemon; its result is discarded."""


def _stdin_esc_waiting() -> bool:
    """True if a lone ESC byte is pending on a TTY stdin. False on non-TTY / error."""
    try:
        if not sys.stdin.isatty():
            return False
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return False
        return sys.stdin.read(1) == "\x1b"
    except Exception:
        return False


def _cbreak_stdin():
    """Context manager putting the TTY into cbreak so a single Esc is readable
    without Enter. No-op when termios is unavailable or stdin is not a TTY."""
    try:
        import termios
        import tty
    except ImportError:
        return contextlib.nullcontext()
    if not sys.stdin.isatty():
        return contextlib.nullcontext()

    @contextlib.contextmanager
    def _ctx():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return _ctx()


def run_with_spinner(
    fn: Callable[[], T],
    verb: str,
    *,
    console: Console | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> T:
    """Run fn() in a worker thread with a live spinner. Returns fn()'s result;
    re-raises fn's exception. Raises Interrupted if the user presses Esc (TTY) or
    Ctrl+C while waiting."""
    console = console or Console()
    cancel_check = cancel_check or _stdin_esc_waiting
    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - propagate to caller
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    try:
        with console.status(f"[{ACCENT}]∑[/] {verb}… (esc 中断)", spinner="dots"):
            with _cbreak_stdin():
                thread.start()
                while thread.is_alive():
                    if cancel_check():
                        raise Interrupted()
                    thread.join(timeout=0.1)
    except KeyboardInterrupt:
        raise Interrupted() from None
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["result"]  # type: ignore[return-value]


def format_stage(text: str) -> str:
    """Status-line text for a workflow stage, with the ∑ brand in accent color."""
    return f"[{ACCENT}]∑[/] {text}"
