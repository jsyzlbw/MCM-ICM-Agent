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
