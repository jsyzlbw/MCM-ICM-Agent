from mcm_agent.agents.discussion import UserDiscussionAgent, confirmed_language
from mcm_agent.agents.modeling import ModelJudge
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult
from mcm_agent.utils.json_io import read_json, write_json


class FakeDecisionLLM:
    """Returns a valid decision (English headings) + a routes tag, with Chinese prose."""

    def generate(self, system, prompt, *, temperature=0.2):
        content = "\n".join(
            [
                "# Model Decision",
                "",
                "## Selected Route",
                "采用多目标决策模型与约束优化结合。",  # Chinese prose on purpose
                "",
                "## Data Requirements",
                "已登记数据。",
                "",
                "## Data Limitations",
                "部分数据采用假设。",
                "",
                "## Figure Requirements",
                "框架图与结果图。",
                "",
                "```routes",
                '{"route_ids": ["multi_objective_decision", "constrained_optimization", "bogus_route"]}',
                "```",
            ]
        )
        return ProviderResult(content=content, metadata={})


def test_route_ids_from_tag_filters_invalid_and_dedupes():
    judge = ModelJudge()
    ids = judge._route_ids_from_tag(
        'prose\n```routes\n{"route_ids": ["forecasting_model", "nope", "forecasting_model"]}\n```\n'
    )
    assert ids == ["forecasting_model"]
    assert judge._route_ids_from_tag("no routes block at all") == []


def test_model_judge_builds_spec_from_tag_even_with_chinese_prose(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    candidates = root / "reports" / "model_candidates.md"
    candidates.parent.mkdir(parents=True, exist_ok=True)
    candidates.write_text("# Model Candidates\n\n多目标动态规划等候选方案。\n", encoding="utf-8")

    ModelJudge(FakeDecisionLLM()).run(root, candidates)

    spec = read_json(root / "reports" / "experiment_spec.json", {})
    route_ids = [e["route_id"] for e in spec.get("experiments", [])]
    assert route_ids, "experiment spec must not be empty"
    assert "multi_objective_decision" in route_ids
    assert "constrained_optimization" in route_ids
    assert "bogus_route" not in route_ids


def test_confirm_direction_locks_language(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    UserDiscussionAgent().confirm_direction(
        root,
        mode="ai_led",
        user_idea_summary="x",
        selected_route="r",
        paper_outline="o",
        decisions_to_preserve=[],
        language="zh",
    )
    lock = read_json(root / "discussion" / "direction_lock.json", {})
    assert lock["language"] == "zh"
    assert confirmed_language(root) == "zh"
    assert confirmed_language(tmp_path / "missing") == "en"  # default
    confirmed = (root / "discussion" / "confirmed_direction.md").read_text(encoding="utf-8")
    assert "## Output Language" in confirmed and "zh" in confirmed


def test_confirm_direction_adopts_assumptions_for_unknown_uncovered_data(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    write_json(
        root / "data" / "data_feasibility_matrix.json",
        [{"target_dataset": "problem-specific modeling data", "availability": "unknown", "proxy_variables": []}],
    )
    UserDiscussionAgent().confirm_direction(
        root,
        mode="ai_led",
        user_idea_summary="x",
        selected_route="r",
        paper_outline="o",
        decisions_to_preserve=[],
    )
    lock = read_json(root / "discussion" / "direction_lock.json", {})
    assert lock["adopted_reframing_strategy"] == "user_provided_assumptions"
