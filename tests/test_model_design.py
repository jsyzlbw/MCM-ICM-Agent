import json
from pathlib import Path

from mcm_agent.agents.model_design import ModelDesignAgent, _normalize_spec
from mcm_agent.core.model_spec import read_model_spec
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


class _SpecLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        spec = {
            "problem_restatement": "Estimate hidden fan votes for DWTS and compare rules.",
            "subproblems": [
                {
                    "subproblem_id": "q1",
                    "title": "Fan-vote estimation",
                    "approach": "Bayesian latent-variable model",
                    "variables": [{"symbol": "v_i", "meaning": "fan vote share of contestant i"}],
                    "assumptions": ["Weekly votes are independent."],
                    "equations": ["v_i = \\theta_i / \\sum_j \\theta_j"],
                    "algorithm_steps": ["Build elimination constraints", "Solve by MCMC"],
                    "metrics": ["elimination_consistency_rate"],
                    "data_inputs": ["weekly judge scores"],
                }
            ],
        }
        return ProviderResult(content=json.dumps(spec), metadata={})


def _prep(tmp_path: Path) -> Path:
    root = create_workspace(tmp_path / "w").root
    (root / "reports" / "problem_understanding.md").write_text(
        "# 题意理解\n估计未知的观众投票，比较 rank 与 percentage。", encoding="utf-8"
    )
    return root


def test_model_design_agent_writes_spec_from_llm(tmp_path: Path) -> None:
    root = _prep(tmp_path)

    ModelDesignAgent(_SpecLLM(), language="en").run(root)

    spec = read_model_spec(root)
    assert spec is not None and spec.subproblems
    assert spec.subproblems[0].approach == "Bayesian latent-variable model"
    assert spec.subproblems[0].metrics == ["elimination_consistency_rate"]
    assert (root / "reports" / "model_spec.md").exists()


def test_normalize_spec_accepts_keyed_subproblem_shape() -> None:
    # The shape DeepSeek actually returns: {subproblem_1: {model_name, description, ...}}
    data = {
        "subproblem_1": {
            "model_name": "Bayesian Hierarchical Generative Model",
            "description": "Infers weekly audience votes from elimination order.",
            "variables": [{"symbol": "v_i", "meaning": "vote share"}],
            "algorithm": ["Build constraints", "Run MCMC"],
            "metrics": ["elimination_consistency_rate"],
        },
        "subproblem_2": {"model_name": "Rule comparison", "steps": ["apply rank", "apply percent"]},
    }
    spec = _normalize_spec(data)
    assert spec is not None
    assert len(spec.subproblems) == 2
    assert spec.subproblems[0].approach == "Bayesian Hierarchical Generative Model"
    assert spec.subproblems[0].metrics == ["elimination_consistency_rate"]
    assert spec.subproblems[0].algorithm_steps == ["Build constraints", "Run MCMC"]
    assert spec.subproblems[1].algorithm_steps == ["apply rank", "apply percent"]


def test_model_design_agent_fallback_without_llm(tmp_path: Path) -> None:
    root = _prep(tmp_path)

    ModelDesignAgent(None).run(root)

    spec = read_model_spec(root)
    assert spec is not None and spec.subproblems  # deterministic fallback spec exists


class _CodeSpecLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        # Describes the ACTUAL code it was shown.
        spec = {
            "subproblems": [
                {
                    "subproblem_id": "q1",
                    "title": "Fan-vote estimation via constrained least squares",
                    "approach": "Constrained least squares from elimination order",
                    "algorithm_steps": ["Reshape weekly scores", "Solve least squares"],
                    "metrics": ["elimination_consistency_rate"],
                }
            ]
        }
        return ProviderResult(content=json.dumps(spec), metadata={})


def test_refine_from_code_overwrites_spec_from_real_code(tmp_path: Path) -> None:
    root = _prep(tmp_path)
    code_dir = root / "code" / "experiments"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "problem1.py").write_text(
        "import pandas as pd\n# constrained least squares fan-vote estimation\n", encoding="utf-8"
    )
    (root / "results" / "model_metrics.json").write_text(
        '{"elimination_consistency_rate": 0.81}', encoding="utf-8"
    )

    spec = ModelDesignAgent(_CodeSpecLLM(), language="en").refine_from_code(root)

    assert spec is not None and spec.subproblems
    assert "least squares" in spec.subproblems[0].approach.lower()
    assert read_model_spec(root).subproblems[0].approach == spec.subproblems[0].approach


def test_refine_from_code_noop_without_code(tmp_path: Path) -> None:
    root = _prep(tmp_path)
    assert ModelDesignAgent(_CodeSpecLLM()).refine_from_code(root) is None


# ---------------------------------------------------------------------------
# SC1 tests: _design prompt must demand one-subproblem-per-task coverage
# ---------------------------------------------------------------------------


class _RecordingLLM:
    """Records the system + prompt strings passed to generate, then returns a
    minimal valid 1-subproblem spec so _normalize_spec succeeds."""

    def __init__(self) -> None:
        self.recorded_system: str = ""
        self.recorded_prompt: str = ""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.recorded_system = system
        self.recorded_prompt = prompt
        spec = {
            "problem_restatement": "Test problem.",
            "subproblems": [
                {
                    "subproblem_id": "q1",
                    "title": "Task 1",
                    "approach": "method",
                    "variables": [],
                    "assumptions": [],
                    "equations": [],
                    "algorithm_steps": ["step"],
                    "metrics": ["m1"],
                }
            ],
        }
        return ProviderResult(content=json.dumps(spec), metadata={})


def test_design_prompt_demands_one_subproblem_per_task(tmp_path: Path) -> None:
    """_design must send a prompt/system that explicitly instructs the LLM to
    create exactly one subproblem per task and not to merge or omit any task."""
    root = _prep(tmp_path)
    recorder = _RecordingLLM()
    ModelDesignAgent(recorder, language="en").run(root)

    combined = (recorder.recorded_system + " " + recorder.recorded_prompt).lower()

    # Must instruct: enumerate tasks first
    assert any(
        phrase in combined for phrase in ("list every", "list all", "enumerate", "extract every", "extract all")
    ), "prompt must instruct LLM to enumerate/list all tasks first"

    # Must instruct: one subproblem per task
    assert any(
        phrase in combined
        for phrase in ("one subproblem per task", "one subproblem for each task", "exactly one subproblem per")
    ), "prompt must demand exactly one subproblem per task"

    # Must forbid merging
    assert "do not merge" in combined or "do not combine" in combined, \
        "prompt must say 'do not merge' or 'do not combine'"

    # Must forbid omitting
    assert "do not omit" in combined or "do not skip" in combined, \
        "prompt must say 'do not omit' or 'do not skip'"

    # Must mention typical task count to guard against 1-subproblem collapse
    assert any(
        phrase in combined
        for phrase in ("3", "4", "5", "typically", "multiple tasks", "several tasks")
    ), "prompt must mention that contest problems typically have multiple tasks"


# ---------------------------------------------------------------------------
# SC3 tests: refine_from_code must handle per-subproblem code files
# ---------------------------------------------------------------------------


class _PerFileRefineRecordingLLM:
    """Fake LLM for SC3 tests: records every call (to detect which file was shown)
    and returns a single-subproblem spec whose sub_id echoes the file stem it saw."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # [(system, prompt), ...]

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.calls.append((system, prompt))
        # Extract the sub_id hint from the prompt (we'll embed "FILE: <stem>" in the prompt)
        stem = "q1"
        for line in prompt.splitlines():
            if line.startswith("FILE:"):
                stem = line.split(":", 1)[1].strip()
                break
        spec = {
            "subproblems": [
                {
                    "subproblem_id": stem,
                    "title": f"Model for {stem}",
                    "approach": f"Approach for {stem}",
                    "algorithm_steps": [f"step for {stem}"],
                    "metrics": [f"metric_{stem}"],
                }
            ]
        }
        return ProviderResult(content=json.dumps(spec), metadata={})


def test_refine_from_code_keeps_all_subproblems(tmp_path: Path) -> None:
    """When code/experiments/ has q1.py and q2.py (plus problem1.py alias),
    refine_from_code must yield a spec with 2 subproblems (q1 and q2), NOT
    collapse to 1 subproblem by only reading problem1.py."""
    root = _prep(tmp_path)
    code_dir = root / "code" / "experiments"
    code_dir.mkdir(parents=True, exist_ok=True)

    (code_dir / "q1.py").write_text("# q1 code\nresult = 1\n", encoding="utf-8")
    (code_dir / "q2.py").write_text("# q2 code\nresult = 2\n", encoding="utf-8")
    # problem1.py is the alias copy of q1 (SC2 produces this)
    (code_dir / "problem1.py").write_text("# q1 code\nresult = 1\n", encoding="utf-8")

    # Nested per-sub metrics (SC2 format)
    metrics = {"q1": {"metric_q1": 0.9}, "q2": {"metric_q2": 0.8}}
    (root / "results" / "model_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

    llm = _PerFileRefineRecordingLLM()
    agent = ModelDesignAgent(llm, language="en")
    spec = agent.refine_from_code(root)

    assert spec is not None, "refine_from_code returned None"
    assert len(spec.subproblems) == 2, (
        f"Expected 2 subproblems (one per per-sub file), got {len(spec.subproblems)}: "
        f"{[s.subproblem_id for s in spec.subproblems]}"
    )
    ids = {s.subproblem_id for s in spec.subproblems}
    assert ids == {"q1", "q2"}, f"Expected sub ids {{q1, q2}}, got {ids}"


def test_refine_from_code_single_file_fallback(tmp_path: Path) -> None:
    """When only problem1.py exists (no per-sub files), refine_from_code must fall
    back to the old single-file behavior and return a spec with at least 1 subproblem."""
    root = _prep(tmp_path)
    code_dir = root / "code" / "experiments"
    code_dir.mkdir(parents=True, exist_ok=True)
    # Only the alias file, no q1.py / q2.py
    (code_dir / "problem1.py").write_text("# single code\nresult = 42\n", encoding="utf-8")
    (root / "results" / "model_metrics.json").write_text('{"some_metric": 0.5}', encoding="utf-8")

    llm = _PerFileRefineRecordingLLM()
    spec = ModelDesignAgent(llm, language="en").refine_from_code(root)

    assert spec is not None, "fallback single-file path returned None"
    assert len(spec.subproblems) >= 1, "Expected at least 1 subproblem in fallback"


def test_normalize_spec_sanitizes_subproblem_id(tmp_path: Path) -> None:
    """_normalize_spec must produce a filesystem-safe subproblem_id even when the
    LLM returns an id with spaces, colons, or other unsafe characters."""
    from mcm_agent.agents.model_design import _normalize_spec

    data = {
        "subproblems": [
            {
                "subproblem_id": "Task 1: estimate",
                "title": "Estimation task",
                "approach": "regression",
            },
            {
                "subproblem_id": "q2",  # already safe
                "title": "Comparison task",
                "approach": "stats",
            },
        ]
    }
    spec = _normalize_spec(data)
    assert spec is not None
    assert len(spec.subproblems) == 2

    # The first id had spaces and colons — must be sanitized
    safe_id = spec.subproblems[0].subproblem_id
    import re
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", safe_id), (
        f"subproblem_id {safe_id!r} is not filesystem-safe"
    )
    # Should NOT contain spaces or colons
    assert " " not in safe_id and ":" not in safe_id

    # The second id was already safe — must be preserved as-is
    assert spec.subproblems[1].subproblem_id == "q2"


class _FourSubproblemLLM:
    """Fake LLM that returns 4 subproblems — mirrors what a 4-task problem
    should produce."""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        spec = {
            "problem_restatement": "A contest problem with four tasks.",
            "subproblems": [
                {
                    "subproblem_id": f"q{i}",
                    "title": f"Task {i}",
                    "approach": f"Method {i}",
                    "variables": [],
                    "assumptions": [],
                    "equations": [],
                    "algorithm_steps": [f"step {i}"],
                    "metrics": [f"metric_{i}"],
                }
                for i in range(1, 5)
            ],
        }
        return ProviderResult(content=json.dumps(spec), metadata={})


def test_design_keeps_all_subproblems_from_llm(tmp_path: Path) -> None:
    """When the LLM returns 4 subproblems, _normalize_spec must preserve all 4
    (no collapse); the final ModelSpec must have exactly 4 subproblems."""
    root = _prep(tmp_path)
    spec = ModelDesignAgent(_FourSubproblemLLM(), language="en").run(root)

    assert spec is not None, "run() returned None"
    assert len(spec.subproblems) == 4, (
        f"Expected 4 subproblems, got {len(spec.subproblems)}"
    )
    ids = [s.subproblem_id for s in spec.subproblems]
    assert ids == ["q1", "q2", "q3", "q4"]
