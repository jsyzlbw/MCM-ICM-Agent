"""Score a workspace's paper against the O-Prize rubric (the O0 measuring stick).

Usage:
    python scripts/score_paper.py <workspace> [--no-llm]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcm_agent.agents.mock_judge import MockJudge, read_paper


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a paper against the O-Prize rubric.")
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--no-llm", action="store_true", help="Use the offline heuristic judge.")
    args = parser.parse_args()

    text, figure_count = read_paper(args.workspace)
    llm = None
    if not args.no_llm:
        try:
            from mcm_agent.config import load_settings
            from mcm_agent.providers.factory import build_provider_bundle

            settings = load_settings(workspace_root=args.workspace)
            bundle = build_provider_bundle(settings, workspace_root=args.workspace)
            llm = bundle.llm
        except Exception:
            llm = None

    score = MockJudge(llm).score(text, figure_count=figure_count)
    print(
        json.dumps(
            {
                "total": score.total,
                "dimensions": score.dimensions,
                "revision_suggestions": score.revision_suggestions,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
