from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def run_smoke(workspace: Path) -> Path:
    workspace = workspace.resolve()
    if workspace.exists():
        shutil.rmtree(workspace)
    create_workspace(workspace)
    session = InteractiveSession(workspace)
    root = Path(__file__).resolve().parents[1]
    problem = root / "examples" / "demo_problem" / "problem.md"
    data = root / "examples" / "demo_problem" / "data" / "sample.csv"
    steps = [
        f"/question {problem}",
        f"/data {data}",
        "/init --llm-key fake-demo-key",
        "/start --lock --run",
    ]
    for step in steps:
        result = session.run_once(step)
        if "required" in result.message.lower() or "Run /question first" in result.message:
            raise RuntimeError(result.message)
    expected = workspace / "output" / "package" / "submission_package.zip"
    if not expected.exists():
        raise RuntimeError(f"missing expected output: {expected}")
    return workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local Mag CLI smoke test.")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--tmp", action="store_true")
    args = parser.parse_args()

    if args.tmp:
        with tempfile.TemporaryDirectory(prefix="mag_cli_smoke_") as tmp:
            workspace = run_smoke(Path(tmp) / "workspace")
            print(f"CLI smoke passed: {workspace}")
        return
    workspace = args.workspace or Path(".mag_cli_smoke")
    result = run_smoke(workspace)
    print(f"CLI smoke passed: {result}")


if __name__ == "__main__":
    main()
