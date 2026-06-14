from pathlib import Path

from mcm_agent.agents.reframing import ResearchReframingAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json
from mcm_agent.utils.json_io import write_json


def test_reframing_agent_generates_proxy_options_for_private_data(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(tmp_path / "run_001")
    write_json(
        workspace.root / "data" / "data_feasibility_matrix.json",
        [
            {
                "need_id": "need_001",
                "target_dataset": "football player salary and bonus contracts",
                "availability": "private_or_unavailable",
                "confidence": 0.9,
                "reason": "Compensation contracts are private.",
                "query": "football player salary and bonus contracts public dataset official",
                "top_urls": [],
                "proxy_variables": [
                    "Player performance statistics",
                    "Market value or transfer fee",
                    "Team revenue, ranking, attendance, or budget class",
                ],
                "recommended_action": "Reframe with proxy variables.",
            }
        ],
    )
    write_json(
        workspace.root / "data" / "search_repair_actions.json",
        [
            {
                "data_need_id": "need_001",
                "target_dataset": "football player salary and bonus contracts",
                "attempted_query": "football player salary and bonus contracts public dataset official",
                "recommended_action": "try_official_api_or_reframe",
                "official_api_candidates": ["World Bank", "OECD", "UNData"],
                "untrusted_urls": ["https://blog.example/salary"],
            }
        ],
    )

    ResearchReframingAgent().run(workspace.root)

    options = read_json(workspace.root / "discussion" / "reframing_options.json", [])
    report = (workspace.root / "discussion" / "reframing_options.md").read_text(
        encoding="utf-8"
    )
    assert options[0]["data_need_id"] == "need_001"
    assert options[0]["strategy"] == "proxy_modeling"
    assert "Market value or transfer fee" in options[0]["proxy_variables"]
    assert any(option["strategy"] == "user_provided_assumptions" for option in options)
    assert "football player salary and bonus contracts" in report
    assert "try_official_api_or_reframe" in report
