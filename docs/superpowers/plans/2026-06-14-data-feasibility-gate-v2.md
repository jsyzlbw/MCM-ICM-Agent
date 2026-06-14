# Data Feasibility Gate v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a structured early data feasibility gate that detects unavailable/private data and proposes proxy variables before the user locks a modeling plan.

**Architecture:** Extend the existing `DataFeasibilityScoutAgent` in place. Keep provider interfaces unchanged, write a new `data/data_feasibility_matrix.json` artifact, and continue to use `route_data_availability` for stage routing.

**Tech Stack:** Python, Pydantic models already in `stage_policy.py`, existing `SearchProvider`, pytest, ruff.

---

### Task 1: Multi-Need Feasibility Matrix

**Files:**
- Modify: `src/mcm_agent/agents/data_feasibility.py`
- Test: `tests/test_data_feasibility.py`

- [ ] **Step 1: Write the failing test**

Add `test_data_feasibility_scout_writes_matrix_for_discussion_data_needs`:

```python
def test_data_feasibility_scout_writes_matrix_for_discussion_data_needs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "The task asks for a disaster response model.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "discussion" / "data_questions.json",
        ["public population data", "football player salary and bonus contracts"],
    )

    class MixedSearchProvider:
        def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
            if "population" in query:
                return [
                    SearchResult(
                        title="Official population data",
                        url="https://data.gov/population",
                        snippet="Official dataset.",
                        score=0.9,
                    )
                ]
            return []

    DataFeasibilityScoutAgent(MixedSearchProvider()).run(workspace.root)

    matrix = read_json(workspace.root / "data" / "data_feasibility_matrix.json", [])
    assert [row["target_dataset"] for row in matrix] == [
        "public population data",
        "football player salary and bonus contracts",
    ]
    assert matrix[0]["availability"] == "available"
    assert matrix[1]["availability"] == "private_or_unavailable"
    assert "Market value or transfer fee" in matrix[1]["proxy_variables"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_data_feasibility.py::test_data_feasibility_scout_writes_matrix_for_discussion_data_needs -q
```

Expected: fail because `data/data_feasibility_matrix.json` is not written.

- [ ] **Step 3: Implement minimal matrix support**

In `DataFeasibilityScoutAgent.run`, derive `target_datasets`, search each need, classify each row, write `data/data_feasibility_matrix.json`, and aggregate the strongest route.

- [ ] **Step 4: Run the focused test**

Run:

```bash
pytest tests/test_data_feasibility.py::test_data_feasibility_scout_writes_matrix_for_discussion_data_needs -q
```

Expected: pass.

### Task 2: Unknown Data Routes To Deep Search

**Files:**
- Modify: `src/mcm_agent/agents/data_feasibility.py`
- Test: `tests/test_data_feasibility.py`

- [ ] **Step 1: Write the failing test**

Add `test_data_feasibility_scout_routes_unknown_need_to_search_data`:

```python
def test_data_feasibility_scout_routes_unknown_need_to_search_data(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    (workspace.root / "reports" / "problem_understanding.md").write_text(
        "The task asks for a custom sports performance index.",
        encoding="utf-8",
    )
    write_json(
        workspace.root / "discussion" / "data_questions.json",
        ["custom sports performance index data"],
    )

    DataFeasibilityScoutAgent(EmptySearchProvider()).run(workspace.root)

    decision = read_json(workspace.root / "reports" / "data_feasibility_decision.json", {})
    assert decision["route"]["next_stage"] == "search_data"
    assert decision["route"]["requires_user_discussion"] is False
```

- [ ] **Step 2: Run the test to verify it fails or proves existing behavior**

Run:

```bash
pytest tests/test_data_feasibility.py::test_data_feasibility_scout_routes_unknown_need_to_search_data -q
```

Expected: pass only if existing aggregate routing already handles unknown needs; otherwise fail and then implement.

- [ ] **Step 3: Implement route aggregation if needed**

Use priority order: `private_or_unavailable` with high confidence, then `proxy_required`, then `unknown`, then `available`.

- [ ] **Step 4: Run all data feasibility tests**

Run:

```bash
pytest tests/test_data_feasibility.py -q
```

Expected: all pass.

### Task 3: Documentation And Workflow Contract

**Files:**
- Modify: `docs/WORKFLOW.md`
- Test: `tests/test_mvp_workflow.py`

- [ ] **Step 1: Update docs**

Document `data/data_feasibility_matrix.json` and explain how user discussion loops through this gate when new data needs appear.

- [ ] **Step 2: Add artifact expectation if required**

If MVP workflow should always create the matrix, add it to the required artifact list in `tests/test_mvp_workflow.py`.

- [ ] **Step 3: Run focused workflow tests**

Run:

```bash
pytest tests/test_data_feasibility.py tests/test_mvp_workflow.py -q
```

Expected: pass.

### Task 4: Verification And Commit

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run full test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run:

```bash
ruff check src tests scripts
```

Expected: all checks pass.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add docs/superpowers/specs/2026-06-14-data-feasibility-gate-v2-design.md docs/superpowers/plans/2026-06-14-data-feasibility-gate-v2.md docs/WORKFLOW.md src/mcm_agent/agents/data_feasibility.py tests/test_data_feasibility.py tests/test_mvp_workflow.py
git commit -m "feat: add data feasibility matrix"
git push
```
