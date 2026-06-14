from pathlib import Path

from mcm_agent.agents.modeling import ModelJudge
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


def test_model_judge_writes_machine_readable_experiment_spec(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    candidates = workspace.root / "reports" / "model_candidates.md"
    candidates.write_text(
        "\n".join(
            [
                "# Model Candidates",
                "",
                "## Problem Type Diagnosis",
                "- Primary problem types: evaluation, optimization",
                "",
                "| Route ID | Candidate | Main Strength |",
                "|---|---|---|",
                "| multi_criteria_evaluation | Entropy-TOPSIS priority scoring | transparent ranking |",
                "| constrained_optimization | Resource allocation model | budget-aware policy |",
            ]
        ),
        encoding="utf-8",
    )

    ModelJudge().run(workspace.root, candidates)

    spec = read_json(workspace.root / "reports" / "experiment_spec.json", {})
    route_ids = [item["route_id"] for item in spec["experiments"]]
    assert spec["version"] == 1
    assert route_ids == ["multi_criteria_evaluation", "constrained_optimization"]
    assert spec["experiments"][0]["solver_module"] == "mcm_agent.solver_modules.evaluation"
    assert spec["experiments"][0]["method"] == "entropy_weighted_topsis"
    assert "results/problem1_results.csv" in spec["experiments"][0]["expected_outputs"]


def test_solver_prefers_experiment_spec_over_markdown_route_detection(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    processed = workspace.root / "data" / "processed" / "sample.csv"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("district,risk,exposure,budget\nA,9,5,10\nB,2,8,6\n", encoding="utf-8")
    (workspace.root / "reports" / "model_decision.md").write_text(
        "# Model Decision\n\n## Selected Route\nBalanced contest-paper route.",
        encoding="utf-8",
    )
    (workspace.root / "reports" / "experiment_spec.json").write_text(
        """
{
  "version": 1,
  "experiments": [
    {
      "route_id": "multi_criteria_evaluation",
      "solver_module": "mcm_agent.solver_modules.evaluation",
      "method": "entropy_weighted_topsis",
      "input_requirements": ["numeric indicators"],
      "expected_outputs": ["results/problem1_results.csv"],
      "metrics": ["priority_score_mean"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    SolverCoderAgent().run(workspace.root)

    result = (workspace.root / "results" / "problem1_results.csv").read_text(encoding="utf-8")
    summary = read_json(workspace.root / "results" / "model_route_summary.json", {})
    assert "priority_score" in result
    assert summary["selected_routes"] == ["multi_criteria_evaluation"]
