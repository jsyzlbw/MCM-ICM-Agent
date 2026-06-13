#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.providers.smoke import ProviderSmokeTester, SmokeStatus


DEFAULT_PROVIDERS = ["llm", "tavily", "firecrawl", "humanizer", "mineru"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test configured MCM Agent providers.")
    parser.add_argument("--env-file", default=".env", help="Path to .env file.")
    parser.add_argument(
        "--workspace",
        default=".smoke",
        help="Directory for temporary smoke outputs.",
    )
    parser.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help="Comma-separated providers: llm,tavily,firecrawl,humanizer,mineru.",
    )
    parser.add_argument(
        "--mineru-file",
        default=None,
        help="Optional PDF/document file for MinerU parse smoke.",
    )
    args = parser.parse_args()

    providers = [item.strip() for item in args.providers.split(",") if item.strip()]
    settings = load_settings(args.env_file)
    tester = ProviderSmokeTester(
        settings,
        workspace_root=Path(args.workspace),
        mineru_file=Path(args.mineru_file) if args.mineru_file else None,
    )
    results = tester.run(providers)
    for result in results:
        print(f"{result.status.value.upper():7} {result.provider:10} {result.detail}")

    failed = [result for result in results if result.status == SmokeStatus.FAILED]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
