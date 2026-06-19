from pathlib import Path

from mcm_agent.agents.discussion import confirmed_language
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


def test_start_language_persists_to_research_script_and_lock(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    problem = tmp_path / "p.md"
    problem.write_text("# Problem\nEstimate fan votes.", encoding="utf-8")
    session = InteractiveSession(root)
    session.run_once(f"/question {problem}")
    session.run_once("/init --llm-key test-key")

    session.run_once("/start --language zh --lock")

    script = read_json(root / "work" / "discussion" / "locked_research_script.json", {})
    assert script.get("language") == "zh"
    assert confirmed_language(root) == "zh"


def test_start_defaults_to_english(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    problem = tmp_path / "p.md"
    problem.write_text("# Problem\n", encoding="utf-8")
    session = InteractiveSession(root)
    session.run_once(f"/question {problem}")
    session.run_once("/init --llm-key test-key")

    session.run_once("/start --lock")

    script = read_json(root / "work" / "discussion" / "locked_research_script.json", {})
    assert script.get("language") == "en"


def test_writer_results_system_prompt_switches_language() -> None:
    agent = PaperWriterAgent()
    agent._language = "zh"
    assert "中文" in agent._results_system_prompt()
    agent._language = "en"
    assert "中文" not in agent._results_system_prompt()
