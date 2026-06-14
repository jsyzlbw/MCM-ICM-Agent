# Data Feasibility Gate v2 Design

## Goal

Upgrade the early data feasibility scout from a single warning report into a structured,
auditable gate that checks whether proposed modeling data can plausibly be obtained before
the user locks the research direction.

## Design

`DataFeasibilityScoutAgent` will derive one or more data needs from discussion data
questions, the problem-understanding report, and obvious private-data markers. For each
need it will run an early official-data search, record the query in `data/retrieval_log.jsonl`,
and write a machine-readable row to `data/data_feasibility_matrix.json`.

Each row records:

- `need_id`
- `target_dataset`
- `query`
- `availability`
- `confidence`
- `reason`
- `top_urls`
- `proxy_variables`
- `recommended_action`

Routing uses the worst actionable row. Available needs continue to `user_discussion`.
Unknown needs route to `search_data` for deeper retrieval. High-confidence private or
unavailable needs route to `research_reframing` and require user discussion before modeling.

## Error Handling

The gate should not pretend private data is public merely because a general webpage exists.
For compensation, contract, payroll, and bonus data, official search results must be credible
public dataset sources. If none are found, the agent proposes proxy variables and reframing.

## Testing

Tests should prove that multiple discussion data needs create multiple feasibility rows,
private compensation data receives proxy suggestions, and an unknown but not private need
routes to deeper `search_data`.
