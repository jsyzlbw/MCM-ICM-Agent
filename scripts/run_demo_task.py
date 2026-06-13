#!/usr/bin/env python
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from mcm_agent.cli import app
from mcm_agent.workflows.demo_report import build_demo_report
from typer.testing import CliRunner


EXAMPLE_ROOT = Path("examples/demo_mcm_task")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bundled demo MCM task.")
    parser.add_argument("--workspace", default=".demo_workspace", help="Output workspace path.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the workspace before running the demo.",
    )
    args = parser.parse_args()
    workspace = Path(args.workspace)
    if args.clean and workspace.exists():
        shutil.rmtree(workspace)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            str(workspace),
            "--problem-file",
            str(EXAMPLE_ROOT / "problem.md"),
            "--attachment",
            str(EXAMPLE_ROOT / "attachments" / "city_flood_indicators.csv"),
            "--user-idea-file",
            str(EXAMPLE_ROOT / "user_idea.md"),
            "--supervisor-skills-dir",
            str(EXAMPLE_ROOT / "skills"),
            "--auto-approve",
        ],
    )
    if result.exit_code != 0:
        print(result.output)
        if result.exception:
            print(f"{result.exception.__class__.__name__}: {result.exception}")
        return result.exit_code or 1

    report = build_demo_report(workspace)
    report_path = workspace / "demo_run_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote report: {report_path}")
    return 0
if __name__ == "__main__":
    sys.exit(main())
