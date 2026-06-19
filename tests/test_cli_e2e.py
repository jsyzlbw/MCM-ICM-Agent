import subprocess
import sys


def test_cli_smoke_script_runs_end_to_end() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_cli_smoke.py", "--tmp"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert "CLI smoke passed" in result.stdout
