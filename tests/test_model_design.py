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
