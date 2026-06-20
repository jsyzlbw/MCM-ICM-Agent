from pathlib import Path

from mcm_agent.core.shell_exec import ShellResult, run_shell


def test_run_shell_captures_stdout_and_exit_zero(tmp_path: Path) -> None:
    result = run_shell(tmp_path, "echo hello")
    assert isinstance(result, ShellResult)
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_run_shell_reports_nonzero_exit(tmp_path: Path) -> None:
    result = run_shell(tmp_path, "exit 3")
    assert result.exit_code == 3


def test_run_shell_runs_in_workspace_cwd(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    result = run_shell(tmp_path, "ls")
    assert "marker.txt" in result.stdout


def test_run_shell_times_out(tmp_path: Path) -> None:
    result = run_shell(tmp_path, "sleep 5", timeout_seconds=1)
    assert result.exit_code == 124
    assert "timed out" in result.stderr.lower()
