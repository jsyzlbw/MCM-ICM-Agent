import sys

import pytest

pexpect = pytest.importorskip("pexpect")


@pytest.mark.skipif(sys.platform == "win32", reason="pty not supported on Windows")
def test_mag_tui_starts_and_runs_shell(tmp_path):
    child = pexpect.spawn(
        sys.executable, ["-m", "mcm_agent.cli"], cwd=str(tmp_path),
        encoding="utf-8", timeout=30, dimensions=(40, 100),
    )
    child.expect_exact("> ")          # welcome panel rendered, prompt docked
    child.sendline("!echo smoke-ok")
    child.expect("smoke-ok")
    child.send("\x04")                # Ctrl-D quits
    child.expect(pexpect.EOF)
