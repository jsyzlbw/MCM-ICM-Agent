"""Real-PTY smoke test for the Textual-based Mag TUI.

Checks:
  (a) Alt-screen is entered  (\\x1b[?1049h)
  (b) A command produces output visible in the TUI
  (c) Input still works after output
  (d) Ctrl+Q exits cleanly (alt-screen restored \\x1b[?1049l)
"""
import sys

import pytest

pexpect = pytest.importorskip("pexpect")


@pytest.mark.skipif(sys.platform == "win32", reason="pty not supported on Windows")
def test_mag_tui_starts_and_runs_shell(tmp_path):
    """
    Verify the Textual TUI:
    (a) enters alt-screen (?1049h)
    (b) processes a shell command and shows output
    (c) input works after output
    (d) ctrl+q exits cleanly (?1049l)
    """
    # Use bytes mode (encoding=None) to detect raw VT sequences reliably
    child = pexpect.spawn(
        sys.executable,
        ["-m", "mcm_agent.cli"],
        cwd=str(tmp_path),
        encoding=None,   # bytes mode for VT sequence detection
        timeout=30,
        dimensions=(40, 120),
    )

    # (a) Check alt-screen entered
    child.expect(b"\x1b\\[\\?1049h", timeout=20)

    # Give the TUI time to render its initial screen
    import time
    time.sleep(1.5)

    # (b) Send a shell command — !echo smoke-ok
    child.send(b"!echo smoke-ok")
    child.send(b"\r")   # Enter key

    # Verify output appears (smoke-ok)
    child.expect(b"smoke-ok", timeout=15)

    # (c) Input still works — send another command
    time.sleep(0.5)
    child.send(b"!echo second-ok")
    child.send(b"\r")
    child.expect(b"second-ok", timeout=10)

    # (d) Ctrl+Q to exit; verify alt-screen restored
    time.sleep(0.3)
    child.send(b"\x11")   # Ctrl+Q
    child.expect(b"\x1b\\[\\?1049l", timeout=10)
    child.expect(pexpect.EOF, timeout=10)
