from __future__ import annotations

from collections import Counter
from pathlib import Path

from mcm_agent.corpus.teardown import TeardownCard
from mcm_agent.utils.json_io import read_json, write_json


def _top(group: list[TeardownCard], field: str, n: int = 15) -> list[dict]:
    """Count how many papers mention each item (deduped within a paper), most common first."""
    counter: Counter = Counter()
    for card in group:
        seen: set[str] = set()
        for item in getattr(card, field):
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                counter[item.strip()] += 1
    return [{"name": name, "papers": count} for name, count in counter.most_common(n)]


def build_patterns(kb_dir: Path) -> dict:
    """Aggregate all teardown cards by problem_type into a reusable pattern library."""
    kb_dir = Path(kb_dir)
    td_dir = kb_dir / "teardowns"
    cards = (
        [TeardownCard(**read_json(p, {})) for p in sorted(td_dir.glob("*.json"))]
        if td_dir.exists()
        else []
    )
    by_type: dict[str, list[TeardownCard]] = {}
    for card in cards:
        by_type.setdefault(card.problem_type, []).append(card)

    out_dir = kb_dir / "patterns"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, int] = {}
    for problem_type, group in by_type.items():
        write_json(
            out_dir / f"{problem_type}.json",
            {
                "problem_type": problem_type,
                "paper_count": len(group),
                "common_models": _top(group, "models_used"),
                "common_techniques": _top(group, "key_techniques"),
                "recurring_pitfalls": _top(group, "pitfalls_or_limitations"),
                "reusable_patterns": _top(group, "reusable_patterns"),
            },
        )
        summary[problem_type] = len(group)
    return summary
