# Real Modeling Capability Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen model selection, experiment specs, solver orchestration, and validation so more MCM/ICM task archetypes get appropriate model structures automatically.

**Architecture:** Keep the existing `ModelingIntelligence`, `ModelJudge`, `ExperimentSpec`, `SolverCoderAgent`, and `ValidationAgent` boundaries. Add a route-planning helper that turns problem-type diagnosis into a richer machine-readable route plan, extend experiment specs with hybrid route metadata, make solver outputs explicitly report route execution status, and make validation route weak-model failures to the right repair stage.

**Tech Stack:** Python 3, Pydantic models, pandas, existing solver modules, pytest, ruff.

---

## Task 1: Route Plan Helper

**Files:**
- Create: `src/mcm_agent/core/model_route_plan.py`
- Modify: `src/mcm_agent/core/modeling_intelligence.py`
- Test: `tests/test_modeling_intelligence.py`

- [ ] **Step 1: Write failing route-plan tests**

Append to `tests/test_modeling_intelligence.py`:

```python
from mcm_agent.core.model_route_plan import build_route_plan


def test_route_plan_marks_hybrid_models_for_multi_type_problems() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Rank districts, optimize limited resources, forecast demand, and simulate uncertainty."
    )

    plan = build_route_plan(diagnosis)

    assert plan.is_hybrid is True
    assert plan.route_ids[:3] == [
        "multi_criteria_evaluation",
        "constrained_optimization",
        "forecasting_model",
    ]
    assert "monte_carlo_simulation" in plan.route_ids
    assert plan.execution_order[0] == "multi_criteria_evaluation"
    assert plan.route_roles["constrained_optimization"] == "decision"


def test_route_plan_limits_routes_to_keep_solver_feasible() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Rank, optimize, forecast, simulate, design a network, and balance multi-objective tradeoffs."
    )

    plan = build_route_plan(diagnosis, max_routes=4)

    assert len(plan.route_ids) == 4
    assert plan.truncated is True
```

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
pytest tests/test_modeling_intelligence.py::test_route_plan_marks_hybrid_models_for_multi_type_problems tests/test_modeling_intelligence.py::test_route_plan_limits_routes_to_keep_solver_feasible -q
```

Expected: fail with `ModuleNotFoundError` for `mcm_agent.core.model_route_plan`.

- [ ] **Step 3: Implement route plan model**

Create `src/mcm_agent/core/model_route_plan.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from mcm_agent.core.modeling_intelligence import ProblemDiagnosis


ROUTE_ROLES = {
    "multi_criteria_evaluation": "screening",
    "constrained_optimization": "decision",
    "forecasting_model": "prediction",
    "monte_carlo_simulation": "uncertainty",
    "network_flow_graph": "structure",
    "multi_objective_decision": "tradeoff",
}

ROUTE_ORDER = [
    "multi_criteria_evaluation",
    "constrained_optimization",
    "forecasting_model",
    "monte_carlo_simulation",
    "network_flow_graph",
    "multi_objective_decision",
]


class ModelRoutePlan(BaseModel):
    route_ids: list[str] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)
    route_roles: dict[str, str] = Field(default_factory=dict)
    is_hybrid: bool = False
    truncated: bool = False


def build_route_plan(diagnosis: ProblemDiagnosis, *, max_routes: int = 4) -> ModelRoutePlan:
    detected = [route.route_id for route in diagnosis.routes]
    ordered = [route_id for route_id in ROUTE_ORDER if route_id in detected]
    truncated = len(ordered) > max_routes
    route_ids = ordered[:max_routes]
    return ModelRoutePlan(
        route_ids=route_ids,
        execution_order=route_ids,
        route_roles={route_id: ROUTE_ROLES.get(route_id, "support") for route_id in route_ids},
        is_hybrid=len(route_ids) > 1,
        truncated=truncated,
    )
```

- [ ] **Step 4: Run modeling intelligence tests**

Run:

```bash
pytest tests/test_modeling_intelligence.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/core/model_route_plan.py tests/test_modeling_intelligence.py
git commit -m "feat: add model route planning helper"
```

---

## Task 2: Experiment Spec Hybrid Metadata

**Files:**
- Modify: `src/mcm_agent/core/experiment_spec.py`
- Modify: `src/mcm_agent/agents/modeling.py`
- Test: `tests/test_experiment_spec.py`
- Test: `tests/test_modeling.py`

- [ ] **Step 1: Write failing experiment spec tests**

Append to `tests/test_experiment_spec.py`:

```python
def test_experiment_spec_records_hybrid_route_metadata() -> None:
    spec = build_experiment_spec(
        ["multi_criteria_evaluation", "constrained_optimization", "forecasting_model"]
    )

    assert spec.route_plan["is_hybrid"] is True
    assert spec.route_plan["execution_order"] == [
        "multi_criteria_evaluation",
        "constrained_optimization",
        "forecasting_model",
    ]
    assert spec.experiments[1].role == "decision"
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
pytest tests/test_experiment_spec.py::test_experiment_spec_records_hybrid_route_metadata -q
```

Expected: fail because `ExperimentSpec.route_plan` and `ExperimentSpecItem.role` do not exist.

- [ ] **Step 3: Extend experiment spec models**

Modify `src/mcm_agent/core/experiment_spec.py`:

```python
class ExperimentSpecItem(BaseModel):
    route_id: str
    solver_module: str
    method: str
    role: str = "support"
    input_requirements: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    column_bindings: dict[str, str | list[str]] = Field(default_factory=dict)


class ExperimentSpec(BaseModel):
    version: int = 1
    route_plan: dict[str, object] = Field(default_factory=dict)
    experiments: list[ExperimentSpecItem] = Field(default_factory=list)
```

Update `build_experiment_spec`:

```python
from mcm_agent.core.model_route_plan import ROUTE_ROLES


def build_experiment_spec(route_ids: list[str]) -> ExperimentSpec:
    experiments = []
    selected = [route_id for route_id in route_ids if route_id in ROUTE_EXPERIMENTS]
    for route_id in selected:
        item = ROUTE_EXPERIMENTS[route_id].model_copy(deep=True)
        experiments.append(item.model_copy(update={"role": ROUTE_ROLES.get(route_id, "support")}))
    return ExperimentSpec(
        route_plan={
            "is_hybrid": len(selected) > 1,
            "execution_order": selected,
            "route_roles": {route_id: ROUTE_ROLES.get(route_id, "support") for route_id in selected},
        },
        experiments=experiments,
    )
```

- [ ] **Step 4: Update `ModelJudge` to use route plan helper**

In `src/mcm_agent/agents/modeling.py`, import:

```python
from mcm_agent.core.model_route_plan import build_route_plan
```

In `ModelJudge.run`, replace:

```python
experiment_spec = build_experiment_spec(
    self._selected_route_ids_for_spec(decision, diagnosis)
)
```

with:

```python
route_plan = build_route_plan(diagnosis)
selected_route_ids = self._selected_route_ids_for_spec(decision, diagnosis) or route_plan.route_ids
experiment_spec = build_experiment_spec(selected_route_ids)
```

- [ ] **Step 5: Run experiment and modeling tests**

Run:

```bash
pytest tests/test_experiment_spec.py tests/test_modeling.py tests/test_modeling_intelligence.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/mcm_agent/core/experiment_spec.py src/mcm_agent/agents/modeling.py tests/test_experiment_spec.py
git commit -m "feat: add hybrid metadata to experiment specs"
```

---

## Task 3: Solver Route Execution Status

**Files:**
- Modify: `src/mcm_agent/agents/solver.py`
- Test: `tests/test_solver_evidence.py`

- [ ] **Step 1: Write failing solver status test**

Append to `tests/test_solver_evidence.py`:

```python
def test_solver_records_route_execution_status_for_hybrid_specs(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text(
        "district,risk,exposure,budget,period,demand\nA,9,5,10,1,10\nB,2,8,6,2,12\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        build_experiment_spec([
            "multi_criteria_evaluation",
            "constrained_optimization",
            "forecasting_model",
            "monte_carlo_simulation",
        ]).model_dump_json(indent=2),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    status = summary["route_execution_status"]
    assert status["multi_criteria_evaluation"] == "executed"
    assert status["constrained_optimization"] == "executed"
    assert status["forecasting_model"] == "executed"
    assert status["monte_carlo_simulation"] == "executed"
```

Add import:

```python
from mcm_agent.core.experiment_spec import build_experiment_spec
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
pytest tests/test_solver_evidence.py::test_solver_records_route_execution_status_for_hybrid_specs -q
```

Expected: fail because `route_execution_status` is missing.

- [ ] **Step 3: Add route execution status in solver summary**

In `src/mcm_agent/agents/solver.py`, add helper:

```python
def _route_execution_status(
    self,
    selected_routes: list[str],
    route_metrics: dict[str, dict[str, object]],
    binding_report: dict[str, object],
) -> dict[str, str]:
    missing = set(binding_report.get("missing_bindings", [])) if isinstance(binding_report.get("missing_bindings"), list) else set()
    status: dict[str, str] = {}
    for route_id in selected_routes:
        if any(str(item).startswith(route_id + ".") for item in missing):
            status[route_id] = "blocked_missing_binding"
        elif any(payload.get("route_id") == route_id for payload in route_metrics.values()):
            status[route_id] = "executed"
        else:
            status[route_id] = "attempted_no_metric"
    return status
```

When writing `model_route_summary.json`, include:

```python
"route_execution_status": self._route_execution_status(
    selected_routes,
    route_metrics,
    binding_report,
),
```

- [ ] **Step 4: Run solver tests**

Run:

```bash
pytest tests/test_solver_evidence.py tests/test_solver_modules.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/agents/solver.py tests/test_solver_evidence.py
git commit -m "feat: record solver route execution status"
```

---

## Task 4: Model-Specific Validation Routing

**Files:**
- Modify: `src/mcm_agent/agents/validation.py`
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write failing validation routing tests**

Append to `tests/test_validation.py`:

```python
def test_validation_routes_missing_solver_bindings_to_modeling_when_spec_is_wrong(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(workspace.root / "results" / "model_metrics.json", {"row_count": 2})
    write_json(
        workspace.root / "results" / "evidence_registry.json",
        [{"evidence_id": "metric_row_count", "source_path": "results/model_metrics.json"}],
    )
    write_json(
        workspace.root / "results" / "solver_binding_report.json",
        {
            "status": "fail",
            "missing_bindings": [
                "network_flow_graph.source_column",
                "network_flow_graph.target_column",
            ],
        },
    )

    ValidationAgent().run(workspace.root)

    gate = read_json(workspace.root / "review" / "validation_gate.json", {})
    assert gate["failure_reason"] == "weak_model"
    assert gate["repair_stage"] == "modeling_council"
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
pytest tests/test_validation.py::test_validation_routes_missing_solver_bindings_to_modeling_when_spec_is_wrong -q
```

Expected: fail because binding failures currently route to `solver_coder`.

- [ ] **Step 3: Add repair-stage selection helper**

In `src/mcm_agent/agents/validation.py`, add:

```python
def _repair_stage_for_blockers(self, *, binding_failure: bool, blocking_issues: list[str]) -> str | None:
    if not blocking_issues:
        return None
    if binding_failure:
        return "modeling_council"
    return "solver_coder"
```

Update `record_gate_decision`:

```python
repair_stage=self._repair_stage_for_blockers(
    binding_failure=binding_failure,
    blocking_issues=blocking_issues,
),
```

- [ ] **Step 4: Run validation tests**

Run:

```bash
pytest tests/test_validation.py tests/test_gate_decisions.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mcm_agent/agents/validation.py tests/test_validation.py
git commit -m "feat: route weak model validation failures"
```

---

## Task 5: End-To-End Archetype Tests

**Files:**
- Modify: `tests/test_mvp_workflow.py`
- Test: `tests/test_mvp_workflow.py`

- [ ] **Step 1: Add archetype workflow tests**

Append to `tests/test_mvp_workflow.py`:

```python
def test_run_mvp_workflow_selects_forecast_simulation_network_routes(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "network_demand.csv"
    problem.write_text(
        "# Problem\n\nForecast evacuation demand, simulate uncertainty, and route traffic through a network.",
        encoding="utf-8",
    )
    attachment.write_text(
        "source,target,cost,period,demand\nA,B,1,1,10\nB,C,2,2,12\nA,C,5,3,14\n",
        encoding="utf-8",
    )
    providers = ProviderBundle(
        llm=FakeLLMProvider({"default": ""}),
        mineru=InjectedMinerUProvider(),
        search=InjectedSearchProvider(),
        extractor=InjectedExtractProvider(),
        official_data=None,
        humanizer=FakeHumanizerProvider({}),
        latex=InjectedLatexProvider(),
    )

    run_mvp_workflow(
        workspace,
        TaskInput(problem_file=problem, attachments=[attachment]),
        providers=providers,
        auto_approve=True,
    )

    summary = read_json(workspace / "results" / "model_route_summary.json", {})
    assert "forecasting_model" in summary["selected_routes"]
    assert "monte_carlo_simulation" in summary["selected_routes"]
    assert "network_flow_graph" in summary["selected_routes"]
    assert summary["route_execution_status"]["forecasting_model"] == "executed"
```

- [ ] **Step 2: Run archetype workflow test**

Run:

```bash
pytest tests/test_mvp_workflow.py::test_run_mvp_workflow_selects_forecast_simulation_network_routes -q
```

Expected: pass after Tasks 1-4. If it fails because route diagnosis misses keywords, add focused keywords to `ModelingIntelligence._problem_types` and a unit test in `tests/test_modeling_intelligence.py`.

- [ ] **Step 3: Run route-related tests**

Run:

```bash
pytest tests/test_mvp_workflow.py tests/test_modeling_intelligence.py tests/test_experiment_spec.py tests/test_solver_evidence.py tests/test_validation.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_mvp_workflow.py src/mcm_agent/core/modeling_intelligence.py
git commit -m "test: cover route archetype workflow"
```

---

## Task 6: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- Route planning helper and hybrid route metadata.
- `reports/experiment_spec.json` now records `route_plan`.
- `results/model_route_summary.json` now records `route_execution_status`.
- Validation routes missing binding weak-model failures to `modeling_council`.
- C route is complete; D route official data API expansion is next.

- [ ] **Step 2: Run full tests**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run lint**

Run:

```bash
ruff check src tests scripts
```

Expected: `All checks passed!`

- [ ] **Step 4: Commit docs**

```bash
git add README.md docs/WORKFLOW.md docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: describe real modeling capability route"
```

- [ ] **Step 5: Push**

```bash
git status --short --branch
git push origin main
```

Expected: `main` pushes cleanly to GitHub.

---

## Acceptance Criteria

- Multi-type problems produce a bounded hybrid `ModelRoutePlan`.
- `reports/experiment_spec.json` contains route plan metadata and route roles.
- `SolverCoderAgent` records `route_execution_status` for every selected route.
- Validation routes binding-driven weak-model failures to `modeling_council`.
- End-to-end workflow test proves a forecast + simulation + network problem selects and executes the matching routes.
- Full verification passes:

```bash
pytest -q
ruff check src tests scripts
```

## Self-Review

- Spec coverage: This plan covers C route planning, experiment specs, solver execution status, validation routing, workflow archetype coverage, docs, and verification.
- Placeholder scan: clean.
- Type consistency: `ModelRoutePlan`, `route_plan`, `role`, and `route_execution_status` are consistently named throughout.
