"""Calibrate MockJudge against REAL Outstanding papers.

The KB (corpus_kb/) holds 451 real MCM/ICM Outstanding papers as Markdown. We score a
stratified sample with the SAME judge mag uses on its own papers, to answer the only
question that matters: "is mag's ~7.0 actually Outstanding-level, or is our judge optimistic?"

Usage:
    python scripts/calibrate_judge.py [--per-type 2] [--samples 3] [--config mcm_agent_config.local.json]

Outputs a per-dimension + total distribution over the real-O sample, and the gap to a
reference mag score (--mag-total, default 7.0). NOTE: papers are scored from MinerU
Markdown (figures are lost), so the `figures` dim understates real papers — flagged below.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", type=Path, default=REPO / "corpus_kb")
    ap.add_argument("--per-type", type=int, default=2, help="papers sampled per problem_type")
    ap.add_argument("--samples", type=int, default=3, help="judge consensus samples per paper")
    ap.add_argument("--config", type=str, default="mcm_agent_config.local.json")
    ap.add_argument("--mag-total", type=float, default=7.0)
    ap.add_argument("--max-chars", type=int, default=60000)
    args = ap.parse_args()

    from mcm_agent.agents.mock_judge import DIMENSIONS, MockJudge
    from mcm_agent.config import load_settings
    from mcm_agent.providers.factory import build_provider_bundle

    settings = load_settings(config_file=args.config)
    bundle = build_provider_bundle(settings, workspace_root=args.kb)
    judge = MockJudge(bundle.llm)
    print(f"judge model: {settings.openai_model}")

    manifest = json.loads((args.kb / "manifest.json").read_text())
    # Stratified deterministic sample: first --per-type papers of each problem_type.
    by_type: dict[str, list[dict]] = {}
    for e in manifest:
        by_type.setdefault(str(e.get("problem_type", "unknown")), []).append(e)
    sample: list[dict] = []
    for ptype, entries in sorted(by_type.items()):
        if ptype == "unknown":
            continue
        sample.extend(sorted(entries, key=lambda e: str(e.get("paper_id")))[: args.per_type])

    print(f"scoring {len(sample)} real Outstanding papers ({args.per_type}/type), "
          f"consensus n={args.samples} ...\n")

    rows: list[dict] = []
    for e in sample:
        pid = str(e.get("paper_id"))
        md = args.kb / "markdown" / f"{pid}.md"
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8")[: args.max_chars]
        fig = text.count("![")  # rough: MinerU image refs
        score = judge.score_consensus(text, figure_count=fig, language="en", samples=args.samples)
        rows.append({"paper_id": pid, "type": e.get("problem_type"),
                     "total": score.total, "dims": score.dimensions})
        print(f"  {pid:>14} [{str(e.get('problem_type')):>18}]  total={score.total:>4}  figs~{fig}")

    if not rows:
        print("no papers scored")
        return

    totals = [r["total"] for r in rows]
    print("\n=== REAL OUTSTANDING (our judge) ===")
    print(f"  n={len(rows)}  total: mean={st.mean(totals):.2f}  "
          f"median={st.median(totals):.2f}  min={min(totals)}  max={max(totals)}")
    print("  per-dimension mean:")
    for d in DIMENSIONS:
        vals = [r["dims"].get(d, 0) for r in rows]
        print(f"    {d:>18}: {st.mean(vals):.1f}")
    print(f"\n=== GAP ===\n  mag(ref)={args.mag_total}  real-O mean={st.mean(totals):.2f}  "
          f"gap={st.mean(totals) - args.mag_total:+.2f}")
    out = args.kb / "_scripts" / "judge_calibration.json"
    out.write_text(json.dumps({"sample": rows, "mag_ref": args.mag_total}, indent=2), encoding="utf-8")
    print(f"\n  written {out}")


if __name__ == "__main__":
    main()
