import json
from pathlib import Path

from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult
from mcm_agent.utils.json_io import read_json


class _ScriptLLM:
    """Fake LLM returning a fixed python script in a fenced block."""

    def __init__(self, script: str, *, fail_first: bool = False):
        self.script = script
        self.fail_first = fail_first
        self.calls = 0

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.calls += 1
        body = self.script
        if self.fail_first and self.calls == 1:
            body = "raise SystemExit('boom')\n"
        return ProviderResult(content=f"```python\n{body}\n```", metadata={})


GOOD_SCRIPT = """
import json
from pathlib import Path
import pandas as pd
ws = Path.cwd()
df = pd.read_csv(sorted((ws / 'data' / 'processed').glob('*.csv'))[0])
df['estimate'] = 1.0
df.to_csv(ws / 'results' / 'problem1_results.csv', index=False)
(ws / 'results' / 'model_metrics.json').write_text(
    json.dumps({'elimination_consistency_rate': 0.91, 'rows': int(len(df))}), encoding='utf-8')
"""


def _prepare(tmp_path: Path) -> Path:
    root = create_workspace(tmp_path / "ws").root
    (root / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (root / "data" / "processed" / "data.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    (root / "reports" / "problem_understanding.md").write_text(
        "# understanding\nestimate hidden votes", encoding="utf-8"
    )
    return root


def test_llm_codegen_produces_task_metrics(tmp_path: Path) -> None:
    root = _prepare(tmp_path)

    SolverCoderAgent(_ScriptLLM(GOOD_SCRIPT)).run(root)

    metrics = read_json(root / "results" / "model_metrics.json", {})
    assert metrics.get("elimination_consistency_rate") == 0.91
    evidence = read_json(root / "results" / "evidence_registry.json", [])
    assert any(e.get("evidence_id") == "metric_elimination_consistency_rate" for e in evidence)


def test_llm_codegen_self_repairs_then_succeeds(tmp_path: Path) -> None:
    root = _prepare(tmp_path)
    llm = _ScriptLLM(GOOD_SCRIPT, fail_first=True)

    SolverCoderAgent(llm).run(root)

    assert llm.calls >= 2  # repaired after the first failing attempt
    metrics = read_json(root / "results" / "model_metrics.json", {})
    assert metrics.get("elimination_consistency_rate") == 0.91
    # Failed repair attempts must be pruned from the run log so the validation
    # gate does not flag them as pipeline failures.
    runs_path = root / "results" / "experiment_runs.jsonl"
    lines = [line for line in runs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    assert all(json.loads(line)["exit_code"] == 0 for line in lines)


def test_llm_codegen_falls_back_to_baseline_when_unfixable(tmp_path: Path) -> None:
    root = _prepare(tmp_path)

    class _AlwaysBad:
        def generate(self, system: str, prompt: str) -> ProviderResult:
            return ProviderResult(content="```python\nraise SystemExit('always')\n```", metadata={})

    SolverCoderAgent(_AlwaysBad()).run(root)

    # baseline still produced the standard outputs
    assert (root / "results" / "problem1_results.csv").exists()
    assert (root / "results" / "model_metrics.json").exists()


def test_llm_codegen_falls_back_when_generation_errors(tmp_path: Path) -> None:
    root = _prepare(tmp_path)

    class _TimeoutLLM:
        def generate(self, system: str, prompt: str) -> ProviderResult:
            raise TimeoutError("read operation timed out")

    # An LLM timeout during codegen must NOT crash the workflow; fall back to baseline.
    SolverCoderAgent(_TimeoutLLM()).run(root)

    assert (root / "results" / "problem1_results.csv").exists()
    assert (root / "results" / "model_metrics.json").exists()
