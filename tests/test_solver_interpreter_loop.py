from pathlib import Path
import pandas as pd
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.providers.base import ProviderResult
from test_code_interpreter import FakeCodeInterpreter


def _ws(tmp_path):
    (tmp_path / "data" / "processed").mkdir(parents=True)
    pd.DataFrame({"region": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]}).to_csv(
        tmp_path / "data" / "processed" / "d.csv", index=False)
    (tmp_path / "results").mkdir(exist_ok=True)
    (tmp_path / "reports").mkdir(exist_ok=True)
    return tmp_path


class _TwoTurnLLM:
    """Turn 1: emit code that writes the contract outputs. Turn 2: DONE."""
    def __init__(self):
        self.calls = 0
    def generate(self, system, prompt, *, temperature=0.2):
        self.calls += 1
        if self.calls == 1:
            code = (
                "import json, pandas as pd\n"
                "from pathlib import Path\n"
                "df = pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
                "df.to_csv('results/problem1_results.csv', index=False)\n"
                "json.dump({'value_mean': float(df['value'].mean())},"
                " open('results/model_metrics.json','w'))\n"
                "print('metrics written')\n"
            )
            return ProviderResult(content=f"```python\n{code}```", metadata={})
        return ProviderResult(content="DONE", metadata={})


def test_interpreter_loop_writes_outputs_and_notebook(tmp_path):
    ws = _ws(tmp_path)
    agent = SolverCoderAgent(llm_provider=_TwoTurnLLM())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))
    assert ok is True
    assert (ws / "results" / "model_metrics.json").exists()
    assert (ws / "results" / "problem1_results.csv").exists()
    assert (ws / "notebook.ipynb").exists()


def test_interpreter_loop_persists_executed_code_for_refine_from_code(tmp_path):
    """The executed cells MUST be written to code/experiments/problem1.py so
    ModelDesignAgent.refine_from_code can recover the real model (coherence chain).
    Regression guard for the B5 finding where the paper's model section went vacuous
    because problem1.py was never written."""
    ws = _ws(tmp_path)
    agent = SolverCoderAgent(llm_provider=_TwoTurnLLM())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))
    assert ok is True
    script = ws / "code" / "experiments" / "problem1.py"
    assert script.exists(), "executed code must be persisted to code/experiments/problem1.py"
    body = script.read_text(encoding="utf-8")
    # the real solver code (its data read) must be present so refine_from_code sees the model
    assert "model_metrics.json" in body
    assert agent._llm_script_rel == "code/experiments/problem1.py"


def test_interpreter_loop_reflects_on_error_then_succeeds(tmp_path):
    ws = _ws(tmp_path)

    class _ErrThenFix:
        def __init__(self): self.calls = 0
        def generate(self, system, prompt, *, temperature=0.2):
            self.calls += 1
            if self.calls == 1:
                return ProviderResult(content="```python\nraise ValueError('oops')\n```", metadata={})
            if self.calls == 2:
                # transcript must contain the real error we fed back
                assert "ValueError" in prompt and "oops" in prompt
                code = ("import json,pandas as pd\nfrom pathlib import Path\n"
                        "df=pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
                        "df.to_csv('results/problem1_results.csv',index=False)\n"
                        "json.dump({'value_mean':float(df['value'].mean())},open('results/model_metrics.json','w'))\n")
                return ProviderResult(content=f"```python\n{code}```", metadata={})
            return ProviderResult(content="DONE", metadata={})

    agent = SolverCoderAgent(llm_provider=_ErrThenFix())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))
    assert ok is True
    assert (ws / "results" / "model_metrics.json").exists()


def test_interpreter_loop_returns_false_when_no_metrics(tmp_path):
    ws = _ws(tmp_path)

    class _NeverWrites:
        def generate(self, system, prompt, *, temperature=0.2):
            return ProviderResult(content="DONE", metadata={})

    agent = SolverCoderAgent(llm_provider=_NeverWrites())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))
    assert ok is False


def _ws_with_two_subproblems(tmp_path):
    """Workspace with a 2-subproblem ModelSpec and the minimal processed CSV."""
    from mcm_agent.core.model_spec import ModelSpec, SubproblemModel, write_model_spec

    ws = _ws(tmp_path)
    (ws / "work" / "discussion").mkdir(parents=True, exist_ok=True)
    spec = ModelSpec(
        subproblems=[
            SubproblemModel(
                subproblem_id="P1",
                title="Ranking",
                approach="TOPSIS",
                metrics=["rank_score"],
            ),
            SubproblemModel(
                subproblem_id="P2",
                title="Forecast",
                approach="Linear regression",
                metrics=["forecast_mae"],
            ),
        ]
    )
    write_model_spec(ws, spec)
    return ws


def test_interpreter_loop_iterates_subproblems(tmp_path):
    """Loop must add_section once per subproblem (2 total)."""
    ws = _ws_with_two_subproblems(tmp_path)

    interp_holder: list[FakeCodeInterpreter] = []

    def _factory(root):
        interp = FakeCodeInterpreter(root)
        interp_holder.append(interp)
        return interp

    write_code = (
        "import json, pandas as pd\n"
        "from pathlib import Path\n"
        "df = pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
        "df.to_csv('results/problem1_results.csv', index=False)\n"
        "json.dump({'rank_score': 0.9, 'forecast_mae': 0.1},"
        " open('results/model_metrics.json', 'w'))\n"
    )

    class _WritesThenDone:
        def __init__(self):
            self.calls = 0

        def generate(self, system, prompt, *, temperature=0.2):
            self.calls += 1
            # First call per subproblem: write outputs; subsequent: DONE
            if self.calls in (1, 3):
                return ProviderResult(content=f"```python\n{write_code}```", metadata={})
            return ProviderResult(content="DONE", metadata={})

    agent = SolverCoderAgent(llm_provider=_WritesThenDone())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=_factory)
    assert ok is True
    assert len(interp_holder) == 1
    interp = interp_holder[0]
    assert len(interp.sections) == 2, f"expected 2 sections, got {interp.sections}"


def test_interpreter_loop_breaks_after_max_errors(tmp_path):
    """A perpetually-erroring LLM must stop at max_errors, not run max_turns cells."""
    ws = _ws(tmp_path)

    interp_holder: list[FakeCodeInterpreter] = []

    def _factory(root):
        interp = FakeCodeInterpreter(root)
        interp_holder.append(interp)
        return interp

    class _AlwaysErrors:
        def generate(self, system, prompt, *, temperature=0.2):
            return ProviderResult(content="```python\nraise ValueError('x')\n```", metadata={})

    agent = SolverCoderAgent(llm_provider=_AlwaysErrors())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=_factory, max_errors=2)
    assert ok is False
    interp = interp_holder[0]
    # Should have broken after max_errors=2 executions, not run all max_turns
    assert len(interp.executed) <= 2, f"expected <=2 executed cells, got {len(interp.executed)}"


def test_extract_code_block_handles_py_tag():
    """_extract_code_block must parse ```py fences (not just ```python)."""
    result = SolverCoderAgent(None)._extract_code_block("```py\nx=1\n```")
    assert result != "", "Expected non-empty result for ```py fence"


# ---------------------------------------------------------------------------
# Task B3: success-path correctness self-eval
# ---------------------------------------------------------------------------

def test_metrics_are_degenerate_unit():
    """Unit tests for _metrics_are_degenerate covering all degenerate cases."""
    agent = SolverCoderAgent(None)

    # empty dict -> degenerate
    ok, reason = agent._metrics_are_degenerate({})
    assert ok is True, "empty dict should be degenerate"
    assert reason  # must give a non-empty reason

    # NaN value -> degenerate
    ok, reason = agent._metrics_are_degenerate({"a": float("nan")})
    assert ok is True, "NaN value should be degenerate"
    assert reason

    # all-zero numerics -> degenerate
    ok, reason = agent._metrics_are_degenerate({"a": 0.0, "b": 0})
    assert ok is True, "all-zero numerics should be degenerate"
    assert reason

    # mixed: one non-zero numeric -> NOT degenerate
    ok, reason = agent._metrics_are_degenerate({"a": 0.0, "b": 0.3})
    assert ok is False, "at least one non-zero finite numeric -> not degenerate"
    assert reason == ""

    # non-numeric values ignored; score=0.5 is fine -> NOT degenerate
    ok, reason = agent._metrics_are_degenerate({"label": "x", "score": 0.5})
    assert ok is False, "non-numeric strings ignored; score=0.5 -> not degenerate"
    assert reason == ""


def test_self_eval_rejects_degenerate_then_continues(tmp_path):
    """Success-path self-eval: loop must re-prompt when DONE is seen with degenerate metrics.

    Script:
      Turn 1 (LLM): writes {"consistency": 0.0} (degenerate) + results csv
      Turn 2 (LLM): says DONE (no code block) -> loop should NOT accept (degenerate),
                    must append corrective message and continue
      Turn 3 (LLM): writes {"consistency": 0.82} (good)
      Turn 4 (LLM): says DONE -> accepted
    """
    ws = _ws(tmp_path)

    class _DegenerateThenFix:
        def __init__(self):
            self.calls = 0

        def generate(self, system, prompt, *, temperature=0.2):
            self.calls += 1
            if self.calls == 1:
                # Write degenerate metrics (all zeros)
                code = (
                    "import json, pandas as pd\n"
                    "from pathlib import Path\n"
                    "df = pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
                    "df.to_csv('results/problem1_results.csv', index=False)\n"
                    "json.dump({'consistency': 0.0}, open('results/model_metrics.json', 'w'))\n"
                    "print('degenerate metrics written')\n"
                )
                return ProviderResult(content=f"```python\n{code}```", metadata={})
            if self.calls == 2:
                # DONE with degenerate metrics - should be rejected
                return ProviderResult(content="DONE", metadata={})
            if self.calls == 3:
                # The corrective message should be in the transcript (prompt)
                assert "[CHECK FAILED]" in prompt, (
                    f"Expected [CHECK FAILED] in transcript at call 3, got: {prompt[-500:]}"
                )
                # Write valid metrics now
                code = (
                    "import json, pandas as pd\n"
                    "from pathlib import Path\n"
                    "df = pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
                    "json.dump({'consistency': 0.82}, open('results/model_metrics.json', 'w'))\n"
                    "print('good metrics written')\n"
                )
                return ProviderResult(content=f"```python\n{code}```", metadata={})
            # Turn 4+: DONE with good metrics -> accepted
            return ProviderResult(content="DONE", metadata={})

    llm = _DegenerateThenFix()
    agent = SolverCoderAgent(llm_provider=llm)
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))

    assert ok is True, "_run_interpreter_loop should return True after re-prompt succeeds"
    assert llm.calls >= 3, (
        f"LLM must be called at least 3 times to prove a re-prompt happened, got {llm.calls}"
    )

    # Final metrics must be non-degenerate
    import json
    metrics = json.loads((ws / "results" / "model_metrics.json").read_text())
    degen, _ = agent._metrics_are_degenerate(metrics)
    assert not degen, f"Final metrics should be non-degenerate, got {metrics}"


def test_self_eval_terminates_when_always_degenerate(tmp_path):
    """Loop must terminate (not hang) when metrics are persistently degenerate.

    Script: odd calls write {"consistency": 0.0} (degenerate), even calls say DONE.
    Because metrics are always degenerate, each DONE at _turn < max_turns-1 is
    rejected and the loop re-prompts — but the loop is bounded by max_turns=6.

    Return value analysis: at the end _run_interpreter_loop checks whether
    results/model_metrics.json is a non-empty dict.  {"consistency": 0.0} IS
    non-empty, so the function returns True even though the metrics are degenerate.
    Downstream validation (not this function) is responsible for catching
    degenerate final metrics.  We therefore assert True here and focus the
    meaningful assertions on boundedness / termination.
    """
    ws = _ws(tmp_path)

    # Capture the interpreter so we can inspect executed-cell count.
    interp_holder: list[FakeCodeInterpreter] = []

    def _factory(root):
        interp = FakeCodeInterpreter(root)
        interp_holder.append(interp)
        return interp

    degenerate_write_code = (
        "import json, pandas as pd\n"
        "from pathlib import Path\n"
        "df = pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
        "df.to_csv('results/problem1_results.csv', index=False)\n"
        "json.dump({'consistency': 0.0}, open('results/model_metrics.json', 'w'))\n"
        "print('degenerate metrics written')\n"
    )

    class _AlwaysDegenerate:
        """Odd calls: write degenerate metrics. Even calls: say DONE.
        Metrics file always stays {"consistency": 0.0} so every DONE is
        rejected by the self-eval gate until max_turns is exhausted."""

        def __init__(self):
            self.calls = 0

        def generate(self, system, prompt, *, temperature=0.2):
            self.calls += 1
            if self.calls % 2 == 1:
                # Odd turn: emit code that (re)writes degenerate metrics
                return ProviderResult(
                    content=f"```python\n{degenerate_write_code}```",
                    metadata={},
                )
            else:
                # Even turn: signal DONE — but metrics are still degenerate,
                # so the self-eval gate re-prompts (until budget runs out)
                return ProviderResult(content="DONE", metadata={})

    llm = _AlwaysDegenerate()
    agent = SolverCoderAgent(llm_provider=llm)

    # Must return without hanging; max_turns=6 caps iteration.
    # Returns True because {"consistency": 0.0} is a non-empty dict (see docstring).
    result = agent._run_interpreter_loop(
        ws,
        interpreter_factory=_factory,
        max_turns=6,
    )

    # --- Boundedness assertions (the key property: no infinite loop) ---
    assert llm.calls <= 7, (
        f"LLM called {llm.calls} times; expected at most max_turns+1=7"
    )
    interp = interp_holder[0]
    assert len(interp.executed) <= 6, (
        f"Interpreter executed {len(interp.executed)} cells; expected <= max_turns=6"
    )

    # --- Return value: True because metrics file is non-empty (see docstring) ---
    assert result is True, (
        "Expected True: {'consistency': 0.0} is a non-empty dict; "
        "degenerate-metric rejection is the caller's responsibility"
    )


# ---------------------------------------------------------------------------
# Task B4: run() degradation chain + evidence registration
# ---------------------------------------------------------------------------

def test_run_uses_interpreter_then_records_evidence(tmp_path):
    """run() with interpreter_factory -> interpreter path -> _record_outputs.

    Asserts:
    - results/evidence_registry.json exists and contains an entry with
      evidence_id "metric_value_mean" (from model_metrics.json key "value_mean").
    - results/model_route_summary.json exists.
    """
    import json as _json
    from mcm_agent.core.workspace import create_workspace

    # Use a fully-initialised workspace so Coordinator.emit() can read task_state.json
    root = create_workspace(tmp_path / "ws").root
    (root / "data" / "processed").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"region": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]}).to_csv(
        root / "data" / "processed" / "d.csv", index=False
    )

    ws = root
    agent = SolverCoderAgent(llm_provider=_TwoTurnLLM())
    agent.run(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))

    # model_route_summary.json must exist (written by _record_outputs)
    route_summary = ws / "results" / "model_route_summary.json"
    assert route_summary.exists(), "results/model_route_summary.json should exist after run()"

    # evidence_registry.json must contain metric_value_mean
    evidence_path = ws / "results" / "evidence_registry.json"
    assert evidence_path.exists(), "results/evidence_registry.json should exist after run()"
    evidence = _json.loads(evidence_path.read_text())
    ids = [entry.get("evidence_id") for entry in evidence]
    assert "metric_value_mean" in ids, (
        f"evidence_registry should contain 'metric_value_mean'; found ids: {ids}"
    )


def test_run_falls_back_to_baseline_when_no_llm(tmp_path):
    """run() with llm_provider=None falls back to _run_templated_baseline.

    The templated baseline always writes results/model_metrics.json.
    """
    from mcm_agent.core.workspace import create_workspace

    # Use the same workspace setup as test_solver_codegen.py's _prepare()
    root = create_workspace(tmp_path / "ws").root
    (root / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (root / "data" / "processed" / "data.csv").write_text(
        "a,b\n1,2\n3,4\n", encoding="utf-8"
    )
    (root / "reports" / "problem_understanding.md").write_text(
        "# understanding\nestimate hidden votes", encoding="utf-8"
    )

    SolverCoderAgent(llm_provider=None).run(root)

    assert (root / "results" / "model_metrics.json").exists(), (
        "Templated baseline should produce results/model_metrics.json"
    )
