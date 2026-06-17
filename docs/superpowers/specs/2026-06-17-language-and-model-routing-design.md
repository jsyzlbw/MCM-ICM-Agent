# Language Selection at Discussion + Robust Model Routing — Design

Status date: 2026-06-17
Status: design agreed with user in conversation; user pre-approved subsequent steps ("中途的设计全部批准").

## 1. Goal

A real run (2026 ICM Problem D, DeepSeek) blocked at `modeling_quality_gate=weak_model` after 3 repair loops. Root cause analysis (from the saved workspace `.mcm_agent_workspaces/2026_icm_d`) found two real defects, both resolvable by deciding more at the `user_discussion` stage plus making model routing language-independent:

1. **Route detection is brittle and language-dependent.** `ModelJudge._diagnosis_from_candidates` / `_selected_route_ids_for_spec` detect archetypes by checking whether the literal internal route-id strings (e.g. `"multi_objective_decision"`) appear in the free-form LLM text. No real LLM emits those identifiers verbatim (the DeepSeek output was fluent Chinese prose), so `experiment_spec.experiments == []` → gate finding "Experiment spec has no selected experiments."
2. **Data-light problems deadlock.** When data feasibility marks a need `unknown` with no proxies and there are no uploaded attachments, `ModelingPlanQualityAgent._data_alignment_issues` blocks unless the direction lock adopted a reframing strategy (`proxy_modeling` / `user_provided_assumptions`). For a problem with no data files and no reframing option, nothing adopts a strategy → permanent block.

Also observed: the LLM answered in Chinese for an English problem because output language is never constrained.

## 2. Decisions (per user)

- **Output language is decided at the `user_discussion` stage** (not hard-coded), defaulting to `runtime.default_language`, and may be changed there (incl. via the GUI Discussion screen later). The user may switch languages (Chinese/English/other).
- Routing must be **language-independent** (work regardless of the chosen output language).
- The user pre-approved the implementation flow.

## 3. Design

### 3.1 Decide language + data strategy at `user_discussion`

`UserDiscussionAgent.confirm_direction` gains a `language: str = "en"` parameter and a data-strategy fallback:

- Write `language` into `discussion/direction_lock.json` (new field on `DiscussionDecision`) and surface it in `confirmed_direction.md` ("## Output Language").
- **Data strategy:** if no reframing option was adopted AND the data feasibility matrix has `unknown`/uncovered needs AND there are no uploaded attachments, lock `adopted_reframing_strategy = "user_provided_assumptions"` and record it in `confirmed_direction.md` ("## Data Strategy: proceed with stated assumptions for uncovered data needs"). This is the human "we'll state assumptions" decision, made explicit at the confirmation stage; it lets `_data_alignment_issues` pass (finding 2) without masking genuinely private data (that path still routes through research reframing).
- The mvp `user_discussion` handler passes `language=settings.mcm_agent_default_language`.

New helper `confirmed_language(workspace_root: Path, default: str = "en") -> str` in `agents/discussion.py` (or a small `core` util) reads `direction_lock.json["language"]`, falling back to `default`.

### 3.2 Modeling agents follow the locked language

`ModelingCouncil.run` and `ModelJudge.run` read the confirmed language and prepend a one-line instruction to their LLM prompts: `"Write all prose in {language} (e.g. 'en'=English, 'zh'=Chinese)."`. Internal identifiers (route ids, headings the parser needs) stay English. Prompts continue to require the existing English structural headings so validation is unchanged.

### 3.3 Language-independent route selection via a structured tag (fixes finding 1)

`ModelJudge._generate_decision` prompt additionally instructs the LLM to append a fenced machine-readable block choosing from the fixed route-id vocabulary:

````
```routes
{"route_ids": ["multi_objective_decision", "constrained_optimization", "forecasting_model"]}
```
````

The prompt lists the 9 valid route ids with one-line English glosses (from `ROUTE_ORDER` / `ROUTE_RECIPES`). New parser `ModelJudge._route_ids_from_tag(decision_text) -> list[str]` extracts the JSON block and keeps only ids present in `ROUTE_EXPERIMENTS`.

`ModelJudge.run` route-id resolution becomes, in priority order:
1. `_route_ids_from_tag(decision)` — the structured tag (language-independent, primary).
2. `_selected_route_ids_for_spec(decision, diagnosis)` — existing literal-id / keyword detection (fallback).
3. If still empty, a safe non-empty default `["multi_criteria_evaluation"]` so a parse miss degrades to a valid (if generic) plan instead of a hard block; a note is recorded in `model_decision.md`.

`build_experiment_spec(resolved_route_ids)` then yields non-empty experiments.

Fallback `_fallback_decision` (used when the LLM is absent/unparseable, e.g. fake provider) is unchanged and still includes literal route ids, so existing tests keep working.

## 4. Affected files

```
src/mcm_agent/core/discussion_state.py     # DiscussionDecision: + language field
src/mcm_agent/agents/discussion.py          # confirm_direction(language=...); data-strategy fallback; confirmed_language() helper
src/mcm_agent/agents/modeling.py            # council/judge follow language; _route_ids_from_tag; route resolution priority
src/mcm_agent/workflows/mvp.py              # user_discussion handler passes language; council/judge already wired
tests/test_modeling_intelligence.py or new tests/test_model_routing.py
tests/test_discussion*.py (new or existing)
```

## 5. Error handling / compatibility

- All new params default safely (`language="en"`); existing callers/tests unaffected.
- Fake-provider path (demo/tests) still emits literal route ids in fallback candidates/decision → existing `test_rag`/`test_mvp_workflow`/modeling tests stay green.
- The structured-tag parser tolerates a missing/malformed block (falls back).
- Data-strategy auto-adopt only triggers for `unknown`/uncovered needs with no attachments and no prior reframing; `private_or_unavailable` still requires real reframing (unchanged).

## 6. Testing

- `FakeEmbedding`-style determinism not needed here; use a fake LLM returning prose + a `routes` block → assert non-empty `experiment_spec.experiments`.
- Parser test: `_route_ids_from_tag` extracts valid ids, ignores invalid ones, tolerates no block.
- Discussion test: `confirm_direction(language="zh")` writes language into `direction_lock.json` + `confirmed_direction.md`; data-strategy fallback sets `user_provided_assumptions` when appropriate.
- Gate test: with a non-empty spec + adopted assumptions strategy, `modeling_quality_gate` passes for a data-light workspace.
- Full suite + ruff green.

## 7. Validation

Resume the saved real run from `modeling_council` with real providers and `--config-file mcm_agent_config.local.json`; expect modeling to pass the quality gate and proceed downstream (data/EDA/solver…). Language follows config (English for ICM-D).

## 8. Out of scope (follow-ups)

- Applying the locked language to every downstream agent (paper_writer, reviewer, claim_planning) — same `confirmed_language()` helper, add incrementally.
- GUI control to pick the language on the Discussion screen.
- LLM-driven route selection beyond the tag (e.g., per-subproblem routing).
