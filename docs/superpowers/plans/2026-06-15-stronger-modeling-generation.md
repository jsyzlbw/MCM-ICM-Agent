# Stronger Modeling Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade modeling from a small fixed route set into a richer, recipe-driven contest modeling planner with additional executable baseline routes.

**Architecture:** Add a deterministic model recipe library that maps problem archetypes to route metadata, solver contracts, validation metrics, and paper-writing guidance. Extend the existing `ModelingIntelligence`, `ModelRoutePlan`, `ExperimentSpec`, and `SolverCoderAgent` contracts rather than creating a separate modeling pipeline. Add three high-value executable baseline routes: classification, clustering/segmentation, and queuing/service-system analysis.

**Tech Stack:** Python 3.12+, Pydantic v2, pandas, numpy, scikit-learn, pytest, ruff.

---

## File Structure

- Create `src/mcm_agent/core/model_recipes.py`: canonical recipe library and lookup helpers.
- Modify `src/mcm_agent/core/modeling_intelligence.py`: use recipes, add problem types `classification`, `clustering`, and `queuing`, expose richer route metadata.
- Modify `src/mcm_agent/core/model_route_plan.py`: route roles/order for new routes.
- Modify `src/mcm_agent/core/experiment_spec.py`: machine-readable solver contracts for new routes.
- Create `src/mcm_agent/solver_modules/classification.py`: deterministic train/test classifier baseline.
- Create `src/mcm_agent/solver_modules/clustering.py`: segmentation baseline.
- Create `src/mcm_agent/solver_modules/queuing.py`: M/M/c style service-system summary.
- Modify `src/mcm_agent/agents/eda.py`: semantic tags for labels, groups, arrivals, service rate, and server count.
- Modify `src/mcm_agent/agents/modeling.py`: candidate and decision prose should include recipe details and solver blueprint.
- Modify `src/mcm_agent/agents/solver.py`: generate route-specific script blocks for new routes and record route metrics/evidence.
- Modify tests: `tests/test_modeling_intelligence.py`, `tests/test_experiment_spec.py`, `tests/test_solver_evidence.py`, `tests/test_mvp_workflow.py`, and new `tests/test_model_recipes.py`.
- Modify docs: `docs/PROJECT_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/WORKFLOW.md`, `README.md`.

## Task 1: Model Recipe Library

**Files:**
- Create: `tests/test_model_recipes.py`
- Create: `src/mcm_agent/core/model_recipes.py`

- [ ] **Step 1: Add failing recipe tests**

Create `tests/test_model_recipes.py`:

```python
from mcm_agent.core.model_recipes import MODEL_RECIPES, recipe_for_problem_type, route_recipe


def test_recipe_library_contains_high_value_contest_archetypes() -> None:
    assert "classification" in MODEL_RECIPES
    assert "clustering" in MODEL_RECIPES
    assert "queuing" in MODEL_RECIPES


def test_route_recipe_exposes_solver_contract() -> None:
    recipe = route_recipe("classification_model")

    assert recipe.route_id == "classification_model"
    assert recipe.solver_module == "mcm_agent.solver_modules.classification"
    assert "classification_accuracy" in recipe.metrics
    assert recipe.column_bindings["label_column"] == ""


def test_recipe_lookup_by_problem_type() -> None:
    recipe = recipe_for_problem_type("queuing")

    assert recipe.route_id == "queuing_service_model"
    assert "arrival rate" in " ".join(recipe.data_needs)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_model_recipes.py -q`

Expected: FAIL with missing module `mcm_agent.core.model_recipes`.

- [ ] **Step 3: Implement recipes**

Create a `ModelRecipe(BaseModel)` with:

```python
problem_type: str
route_id: str
candidate: str
main_strength: str
data_needs: list[str]
methods: list[str]
metrics: list[str]
implementation_risk: str
solver_module: str
method: str
role: str
input_requirements: list[str]
expected_outputs: list[str]
column_bindings: dict[str, str | list[str]]
paper_guidance: list[str]
```

Include recipes for existing routes and new routes:

- `classification` -> `classification_model`, `mcm_agent.solver_modules.classification`, method `logistic_regression_baseline`, metrics `classification_accuracy`, `classification_f1`.
- `clustering` -> `clustering_segmentation`, `mcm_agent.solver_modules.clustering`, method `kmeans_segmentation`, metrics `cluster_count`, `cluster_silhouette`.
- `queuing` -> `queuing_service_model`, `mcm_agent.solver_modules.queuing`, method `mmc_queue_summary`, metrics `queue_utilization`, `expected_wait_time`.

Expose:

```python
MODEL_RECIPES: dict[str, ModelRecipe]
ROUTE_RECIPES: dict[str, ModelRecipe]
recipe_for_problem_type(problem_type: str) -> ModelRecipe
route_recipe(route_id: str) -> ModelRecipe
```

- [ ] **Step 4: Run recipe tests**

Run: `pytest tests/test_model_recipes.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_model_recipes.py src/mcm_agent/core/model_recipes.py
git commit -m "feat: add model recipe library"
```

## Task 2: Recipe-Driven Diagnosis And Experiment Specs

**Files:**
- Modify: `tests/test_modeling_intelligence.py`
- Modify: `tests/test_experiment_spec.py`
- Modify: `src/mcm_agent/core/modeling_intelligence.py`
- Modify: `src/mcm_agent/core/model_route_plan.py`
- Modify: `src/mcm_agent/core/experiment_spec.py`
- Modify: `src/mcm_agent/agents/modeling.py`

- [ ] **Step 1: Add failing diagnosis tests**

Add to `tests/test_modeling_intelligence.py`:

```python
def test_modeling_intelligence_detects_classification_clustering_and_queuing() -> None:
    diagnosis = ModelingIntelligence().diagnose(
        "Classify risk levels, cluster customer segments, and model queue waiting time with service counters."
    )

    route_ids = [route.route_id for route in diagnosis.routes]
    assert "classification" in diagnosis.primary_problem_types
    assert "clustering" in diagnosis.primary_problem_types
    assert "queuing" in diagnosis.primary_problem_types
    assert "classification_model" in route_ids
    assert "clustering_segmentation" in route_ids
    assert "queuing_service_model" in route_ids


def test_modeling_council_fallback_includes_solver_blueprint(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    problem_report = workspace.root / "reports" / "problem_understanding.md"
    direction = workspace.root / "discussion" / "confirmed_direction.md"
    problem_report.write_text(
        "# Report\n\nClassify risk levels and cluster customer groups.",
        encoding="utf-8",
    )
    direction.parent.mkdir(parents=True, exist_ok=True)
    direction.write_text("# Direction\nUse interpretable model recipes.", encoding="utf-8")

    ModelingCouncil().run(workspace.root, problem_report, direction)

    content = (workspace.root / "reports" / "model_candidates.md").read_text(encoding="utf-8")
    assert "## Solver Blueprint" in content
    assert "classification_model" in content
    assert "clustering_segmentation" in content
```

- [ ] **Step 2: Add failing experiment-spec test**

Add to `tests/test_experiment_spec.py`:

```python
def test_experiment_spec_builds_new_recipe_routes() -> None:
    spec = build_experiment_spec(["classification_model", "clustering_segmentation", "queuing_service_model"])

    route_ids = [item.route_id for item in spec.experiments]
    assert route_ids == ["classification_model", "clustering_segmentation", "queuing_service_model"]
    assert spec.experiments[0].solver_module == "mcm_agent.solver_modules.classification"
    assert spec.experiments[0].column_bindings["label_column"] == ""
    assert spec.experiments[2].method == "mmc_queue_summary"
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
pytest tests/test_modeling_intelligence.py::test_modeling_intelligence_detects_classification_clustering_and_queuing \
  tests/test_modeling_intelligence.py::test_modeling_council_fallback_includes_solver_blueprint \
  tests/test_experiment_spec.py::test_experiment_spec_builds_new_recipe_routes -q
```

Expected: FAIL because new problem types and spec routes are missing.

- [ ] **Step 4: Implement recipe-driven diagnosis**

In `modeling_intelligence.py`, build `ModelRoute` from `ModelRecipe` and add keyword scores:

- classification: `classify`, `classification`, `category`, `label`, `risk level`, `binary`, `logistic`.
- clustering: `cluster`, `segmentation`, `segment`, `group`, `unsupervised`, `typology`.
- queuing: `queue`, `waiting time`, `arrival`, `service rate`, `server`, `counter`, `line`.

Keep existing keyword behavior and ordering.

- [ ] **Step 5: Implement route order/roles**

In `model_route_plan.py`, add:

```python
"classification_model": "prediction",
"clustering_segmentation": "structure",
"queuing_service_model": "service"
```

and put these routes in `ROUTE_ORDER` after existing forecasting/simulation where appropriate.

- [ ] **Step 6: Implement experiment spec from recipes**

In `experiment_spec.py`, replace hand-coded `ROUTE_EXPERIMENTS` construction with recipe-derived `ExperimentSpecItem` values while preserving existing route IDs and fields.

- [ ] **Step 7: Add solver blueprint prose**

In `ModelingCouncil._fallback_candidates`, add a `## Solver Blueprint` section listing each route ID, solver module, method, required bindings, and metrics. In `ModelJudge._fallback_decision`, include recipe paper guidance under `## Mathematical Formulation` or a new `## Solver Blueprint` section.

- [ ] **Step 8: Run focused tests**

Run:

```bash
pytest tests/test_model_recipes.py tests/test_modeling_intelligence.py tests/test_experiment_spec.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/test_modeling_intelligence.py tests/test_experiment_spec.py src/mcm_agent/core/modeling_intelligence.py src/mcm_agent/core/model_route_plan.py src/mcm_agent/core/experiment_spec.py src/mcm_agent/agents/modeling.py
git commit -m "feat: drive modeling plans from recipes"
```

## Task 3: New Solver Modules

**Files:**
- Modify: `tests/test_solver_evidence.py`
- Create: `src/mcm_agent/solver_modules/classification.py`
- Create: `src/mcm_agent/solver_modules/clustering.py`
- Create: `src/mcm_agent/solver_modules/queuing.py`

- [ ] **Step 1: Add failing module tests**

Add to `tests/test_solver_evidence.py`:

```python
def test_classification_solver_module_returns_metrics() -> None:
    from mcm_agent.solver_modules.classification import logistic_regression_baseline
    import pandas as pd

    frame = pd.DataFrame(
        {
            "feature_a": [0, 1, 2, 3, 4, 5],
            "feature_b": [0, 1, 1, 2, 2, 3],
            "risk_label": [0, 0, 0, 1, 1, 1],
        }
    )

    predictions, metrics = logistic_regression_baseline(
        frame,
        feature_columns=["feature_a", "feature_b"],
        label_column="risk_label",
    )

    assert "predicted_label" in predictions.columns
    assert metrics["classification_accuracy"] >= 0.5


def test_clustering_solver_module_returns_segments() -> None:
    from mcm_agent.solver_modules.clustering import kmeans_segmentation
    import pandas as pd

    frame = pd.DataFrame({"x": [0, 0.1, 8, 8.2], "y": [0, 0.2, 8, 8.1]})

    segments, metrics = kmeans_segmentation(frame, feature_columns=["x", "y"], n_clusters=2)

    assert "cluster_id" in segments.columns
    assert metrics["cluster_count"] == 2


def test_queuing_solver_module_returns_service_metrics() -> None:
    from mcm_agent.solver_modules.queuing import mmc_queue_summary
    import pandas as pd

    frame = pd.DataFrame({"arrival_rate": [2.0, 2.2], "service_rate": [3.0, 3.1], "servers": [2, 2]})

    summary, metrics = mmc_queue_summary(
        frame,
        arrival_rate_column="arrival_rate",
        service_rate_column="service_rate",
        server_count_column="servers",
    )

    assert "utilization" in summary.columns
    assert metrics["queue_utilization"] < 1
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_solver_evidence.py::test_classification_solver_module_returns_metrics \
  tests/test_solver_evidence.py::test_clustering_solver_module_returns_segments \
  tests/test_solver_evidence.py::test_queuing_solver_module_returns_service_metrics -q
```

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement classification module**

Use `LogisticRegression(max_iter=1000)` when labels have at least two classes. Use deterministic train/test split with `random_state=42`; for tiny datasets, train and evaluate on the same rows. Return dataframe with `predicted_label` and `predicted_probability` where available, plus `classification_accuracy` and `classification_f1`.

- [ ] **Step 4: Implement clustering module**

Use `KMeans(n_clusters=min(n_clusters, len(frame)), random_state=42, n_init=10)` and `StandardScaler`. Return `cluster_id`, `cluster_distance`, and metrics `cluster_count`, `cluster_inertia`, `cluster_silhouette` where computable.

- [ ] **Step 5: Implement queuing module**

Implement stable M/M/c Erlang-C helpers. Return row-level utilization and expected waiting time. Clamp unstable queues to warnings and finite fallback metrics.

- [ ] **Step 6: Run module tests**

Run the three new tests again.

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_solver_evidence.py src/mcm_agent/solver_modules/classification.py src/mcm_agent/solver_modules/clustering.py src/mcm_agent/solver_modules/queuing.py
git commit -m "feat: add classification clustering queuing solvers"
```

## Task 4: Solver Integration For New Routes

**Files:**
- Modify: `tests/test_solver_evidence.py`
- Modify: `tests/test_mvp_workflow.py`
- Modify: `src/mcm_agent/agents/eda.py`
- Modify: `src/mcm_agent/agents/solver.py`

- [ ] **Step 1: Add failing end-to-end solver test**

Add to `tests/test_solver_evidence.py`:

```python
def test_solver_runs_classification_clustering_and_queuing_routes(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text(
        "feature_a,feature_b,risk_label,segment_value,arrival_rate,service_rate,servers\n"
        "0,0,0,1,2.0,3.0,2\n"
        "1,1,0,1.2,2.2,3.1,2\n"
        "4,3,1,8,2.4,3.2,2\n"
        "5,4,1,8.2,2.1,3.0,2\n",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        build_experiment_spec(
            ["classification_model", "clustering_segmentation", "queuing_service_model"]
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    assert (workspace.root / "results" / "classification_results.csv").exists()
    assert (workspace.root / "results" / "cluster_segments.csv").exists()
    assert (workspace.root / "results" / "queue_summary.csv").exists()
    assert "classification_accuracy" in summary["route_metrics"]
    assert "cluster_count" in summary["route_metrics"]
    assert "queue_utilization" in summary["route_metrics"]
```

- [ ] **Step 2: Add failing workflow archetype test**

Add to `tests/test_mvp_workflow.py`:

```python
def test_run_mvp_workflow_selects_classification_clustering_queuing_routes(tmp_path: Path) -> None:
    workspace = tmp_path / "task"
    problem = tmp_path / "problem.md"
    attachment = tmp_path / "service.csv"
    problem.write_text(
        "# Problem\n\nClassify risk levels, cluster service regions, and estimate queue waiting time.",
        encoding="utf-8",
    )
    attachment.write_text(
        "feature_a,feature_b,risk_label,segment_value,arrival_rate,service_rate,servers\n"
        "0,0,0,1,2.0,3.0,2\n"
        "1,1,0,1.2,2.2,3.1,2\n"
        "4,3,1,8,2.4,3.2,2\n"
        "5,4,1,8.2,2.1,3.0,2\n",
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
    assert "classification_model" in summary["selected_routes"]
    assert "clustering_segmentation" in summary["selected_routes"]
    assert "queuing_service_model" in summary["selected_routes"]
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
pytest tests/test_solver_evidence.py::test_solver_runs_classification_clustering_and_queuing_routes \
  tests/test_mvp_workflow.py::test_run_mvp_workflow_selects_classification_clustering_queuing_routes -q
```

Expected: FAIL because solver script lacks new route blocks and semantic binding.

- [ ] **Step 4: Extend EDA semantic tags**

In `DataEDAAgent._semantic_tags`, add:

- `label`: `label`, `class`, `category`, `risk_label`, `target_class`.
- `group`: `segment`, `group`, `region`, `cluster`.
- `arrival_rate`: `arrival`, `arrival_rate`, `lambda`.
- `service_rate`: `service`, `service_rate`, `mu`.
- `server_count`: `servers`, `server_count`, `counter`, `capacity_count`.

- [ ] **Step 5: Extend solver generated script**

In `SolverCoderAgent.run`, import new modules and add route blocks:

- `classification_model`: infer label column, feature columns, write `results/classification_results.csv`, merge `classification_` metrics.
- `clustering_segmentation`: infer feature columns, write `results/cluster_segments.csv`, merge `cluster_` metrics.
- `queuing_service_model`: infer arrival/service/server columns, write `results/queue_summary.csv`, merge `queue_` metrics.

- [ ] **Step 6: Extend column bindings and route metrics**

Add binding inference for new routes. Add required bindings:

- classification: `label_column`
- queuing: `arrival_rate_column`, `service_rate_column`

Copy `classification_`, `cluster_`, and `queue_` prefixed metrics into `route_metrics`.

- [ ] **Step 7: Run focused tests**

Run:

```bash
pytest tests/test_solver_evidence.py tests/test_mvp_workflow.py::test_run_mvp_workflow_selects_classification_clustering_queuing_routes -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tests/test_solver_evidence.py tests/test_mvp_workflow.py src/mcm_agent/agents/eda.py src/mcm_agent/agents/solver.py
git commit -m "feat: execute new modeling recipe routes"
```

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- Model recipe library and supported route types.
- New routes: classification, clustering, queuing.
- Solver blueprint output in `reports/model_candidates.md`.
- New outputs: `classification_results.csv`, `cluster_segments.csv`, `queue_summary.csv`.
- Keep deterministic route modules as contest-safe baselines rather than unrestricted code generation.

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/test_model_recipes.py tests/test_modeling_intelligence.py tests/test_experiment_spec.py tests/test_solver_evidence.py tests/test_mvp_workflow.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
pytest -q
ruff check src tests scripts
```

Expected: PASS.

- [ ] **Step 4: Commit docs**

```bash
git add README.md docs/WORKFLOW.md docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: describe stronger modeling generation"
```

## Self-Review

- Spec coverage: The plan covers recipe library, diagnosis, experiment specs, new solver modules, route execution, evidence metrics, workflow coverage, docs, and verification.
- Placeholder scan: No unresolved TODO/TBD placeholders remain.
- Type consistency: `classification_model`, `clustering_segmentation`, `queuing_service_model`, `ModelRecipe`, `ExperimentSpecItem`, and route metric prefixes are used consistently.
