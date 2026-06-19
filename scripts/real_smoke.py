"""Real-provider smoke test.

Runs the full MVP workflow with REAL providers loaded from a local config file
(default: mcm_agent_config.local.json). This makes real, billable API calls and
is intentionally NOT part of the pytest suite. Run it manually to verify the
end-to-end pipeline against a real problem.

Example:
    python scripts/real_smoke.py \
        --problem assets/diagnostic_2026_mcm_c/problem.md \
        --data assets/diagnostic_2026_mcm_c/2026_MCM_Problem_C_Data.csv \
        --fast
"""

from __future__ import annotations

import argparse
import shutil
import traceback
from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.core.models import TaskInput
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.workflows.mvp import run_mvp_workflow

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-provider smoke (uses local API keys; costs money).")
    parser.add_argument("--problem", type=Path, required=True, help="problem .md/.pdf")
    parser.add_argument("--data", type=Path, action="append", default=[], help="data file(s)")
    parser.add_argument("--workspace", type=Path, default=Path("/tmp/mag_real_smoke"))
    parser.add_argument("--config", type=Path, default=REPO / "mcm_agent_config.local.json")
    parser.add_argument("--fast", action="store_true", help="force mineru fake to skip PDF upload")
    args = parser.parse_args()

    ws = args.workspace.resolve()
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)

    settings = load_settings(config_file=str(args.config))
    if args.fast:
        settings = settings.model_copy(update={"mineru_mode": "fake"})
    print("LLM:", settings.openai_base_url, settings.openai_model, "key_set=", bool(settings.openai_api_key))
    bundle = build_provider_bundle(settings, workspace_root=ws)
    print(
        "providers ->",
        "llm:", type(bundle.llm).__name__,
        "| search:", type(bundle.search).__name__,
        "| latex:", type(bundle.latex).__name__,
    )

    task = TaskInput(problem_file=args.problem, attachments=list(args.data), template_dir=None)
    try:
        run_mvp_workflow(ws, task, providers=bundle, settings=settings, auto_approve=True)
        print("WORKFLOW COMPLETED")
    except Exception:
        print("WORKFLOW RAISED:")
        traceback.print_exc()

    pdf = ws / "paper" / "main.pdf"
    print("PDF:", pdf, pdf.stat().st_size if pdf.exists() else "MISSING")
    package = ws / "final_submission" / "submission_package.zip"
    print("PACKAGE:", package, package.stat().st_size if package.exists() else "MISSING")


if __name__ == "__main__":
    main()
