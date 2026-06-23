export const meta = {
  name: 'mcm-teardown-next',
  description: 'Teardown cards for papers still missing one (subagent drip)',
  phases: [{ title: 'Teardown' }],
}
const SCHEMA = {"type": "object", "properties": {"problem_summary": {"type": "string"}, "models_used": {"type": "array", "items": {"type": "string"}}, "key_techniques": {"type": "array", "items": {"type": "string"}}, "why_it_won": {"type": "string"}, "section_highlights": {"type": "string"}, "pitfalls_or_limitations": {"type": "array", "items": {"type": "string"}}, "reusable_patterns": {"type": "array", "items": {"type": "string"}}}, "required": ["problem_summary", "models_used", "key_techniques", "why_it_won", "section_highlights", "pitfalls_or_limitations", "reusable_patterns"]}
const MD = '/Users/mac/Programming/MCM-ICM-Agent/corpus_kb/markdown'
const papers = [
  { paper_id: "2023-2322687", year: 2023, problem: "A", problem_type: "continuous" }
]
const cards = await parallel(papers.map((p) => () =>
  agent(`You are an experienced MCM/ICM judge and mathematical-modeling coach. Use your Read tool to read the Outstanding (O-award) paper at this absolute path:\n${MD}/${p.paper_id}.md\n\nIt is the ${p.year} MCM/ICM Problem ${p.problem} (problem type: ${p.problem_type}) winning paper. After reading it, produce a structured teardown card SPECIFIC TO THIS PAPER: the concrete models/algorithms it used, key techniques, why it won (judge perspective), what made its writing/structure strong, its pitfalls/limitations, and reusable patterns a future team could adopt. Be concrete and specific — name the actual methods this paper used, not generic advice.`, { label: `td:${p.paper_id}`, phase: 'Teardown', schema: SCHEMA })
    .then((c) => ({ paper_id: p.paper_id, year: p.year, problem: p.problem, problem_type: p.problem_type, ...c }))
))
return { cards: cards.filter(Boolean) }
