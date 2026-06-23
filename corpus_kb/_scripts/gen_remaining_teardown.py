"""Emit a Workflow script for papers that still lack a teardown card.
Run this, then: Workflow({scriptPath: 'corpus_kb/_scripts/teardown_next.js'}); then save_cards.py on the result.
Idempotent across sessions/reboots because the persistent state is the cards on disk."""
import json
from pathlib import Path

from mcm_agent.corpus.manifest import build_manifest

ROOT = "/Users/mac/Programming/MCM-ICM-Agent"
md_dir = Path(f"{ROOT}/corpus_kb/markdown")
td_dir = Path(f"{ROOT}/corpus_kb/teardowns")
have = {p.stem for p in td_dir.glob("*.json")} if td_dir.exists() else set()

entries = [
    x for x in build_manifest(Path(f"{ROOT}/assets/mcm_icm_corpus"))
    if 2004 <= x.year <= 2025 and (md_dir / f"{x.paper_id}.md").exists() and x.paper_id not in have
]
papers = [{"paper_id": x.paper_id, "year": x.year, "problem": x.problem, "problem_type": x.problem_type} for x in entries]

schema = {
    "type": "object",
    "properties": {
        "problem_summary": {"type": "string"},
        "models_used": {"type": "array", "items": {"type": "string"}},
        "key_techniques": {"type": "array", "items": {"type": "string"}},
        "why_it_won": {"type": "string"},
        "section_highlights": {"type": "string"},
        "pitfalls_or_limitations": {"type": "array", "items": {"type": "string"}},
        "reusable_patterns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["problem_summary", "models_used", "key_techniques", "why_it_won",
                 "section_highlights", "pitfalls_or_limitations", "reusable_patterns"],
}
papers_js = ",\n  ".join(
    '{ paper_id: "%s", year: %d, problem: "%s", problem_type: "%s" }'
    % (p["paper_id"], p["year"], p["problem"], p["problem_type"]) for p in papers
)
prompt = (
    "`You are an experienced MCM/ICM judge and mathematical-modeling coach. Use your Read tool to read the "
    "Outstanding (O-award) paper at this absolute path:\\n${MD}/${p.paper_id}.md\\n\\nIt is the ${p.year} "
    "MCM/ICM Problem ${p.problem} (problem type: ${p.problem_type}) winning paper. After reading it, produce a "
    "structured teardown card SPECIFIC TO THIS PAPER: the concrete models/algorithms it used, key techniques, "
    "why it won (judge perspective), what made its writing/structure strong, its pitfalls/limitations, and "
    "reusable patterns a future team could adopt. Be concrete and specific — name the actual methods this "
    "paper used, not generic advice.`"
)
script = """export const meta = {
  name: 'mcm-teardown-next',
  description: 'Teardown cards for papers still missing one (subagent drip)',
  phases: [{ title: 'Teardown' }],
}
const SCHEMA = %s
const MD = '%s/corpus_kb/markdown'
const papers = [
  %s
]
const cards = await parallel(papers.map((p) => () =>
  agent(%s, { label: `td:${p.paper_id}`, phase: 'Teardown', schema: SCHEMA })
    .then((c) => ({ paper_id: p.paper_id, year: p.year, problem: p.problem, problem_type: p.problem_type, ...c }))
))
return { cards: cards.filter(Boolean) }
""" % (json.dumps(schema), ROOT, papers_js, prompt)

out = Path(f"{ROOT}/corpus_kb/_scripts/teardown_next.js")
out.write_text(script)
print(f"remaining papers without cards: {len(papers)}; wrote {out}")
