from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.research_script import build_initial_research_script
from mcm_agent.core.workspace import create_workspace, load_workspace_state
from mcm_agent.providers.base import ProviderResult


class _AnalysisLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        return ProviderResult(
            content="本题要求逆向推断粉丝票数。\n方向一：贝叶斯反演。\n方向二：约束最优化。",
            metadata={},
        )


class _BrokenLLM:
    def generate(self, system: str, prompt: str) -> ProviderResult:
        raise RuntimeError("network down")


def _ready_workspace(tmp_path: Path) -> Path:
    workspace = create_workspace(tmp_path / "workspace")
    problem = tmp_path / "problem.md"
    problem.write_text("# Problem", encoding="utf-8")
    session = InteractiveSession(workspace.root)
    session.run_once(f"/question {problem}")
    session.run_once("/init --llm-key test-key")
    # Use the offline fake LLM so /start's problem analysis never hits the network.
    from mcm_agent.core.config_writer import set_env_var

    set_env_var(workspace.root, "MAG_LLM_PROVIDER", "fake")
    return workspace.root


def test_start_requires_llm(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)

    result = session.run_once("/start")

    assert "LLM API is required" in result.message


def test_start_requires_question_after_llm(tmp_path: Path) -> None:
    workspace = create_workspace(tmp_path / "workspace")
    session = InteractiveSession(workspace.root)
    session.run_once("/init --llm-key test-key")

    result = session.run_once("/start")

    assert "Run /question first" in result.message


def test_start_creates_research_script_draft(tmp_path: Path) -> None:
    root = _ready_workspace(tmp_path)
    session = InteractiveSession(root)

    result = session.run_once("/start")

    assert "Research script draft created" in result.message
    assert (root / "work/discussion/research_script_draft.md").exists()
    assert (root / "work/discussion/research_script_draft.json").exists()
    assert load_workspace_state(root).phase == "discussing"


def test_start_lock_creates_locked_research_script(tmp_path: Path) -> None:
    root = _ready_workspace(tmp_path)
    session = InteractiveSession(root)

    result = session.run_once("/start --lock")

    assert "Research script locked" in result.message
    assert (root / "work/discussion/locked_research_script.md").exists()
    assert (root / "work/discussion/locked_research_script.json").exists()
    assert load_workspace_state(root).phase == "script_locked"


def test_research_script_mentions_data_availability(tmp_path: Path) -> None:
    root = _ready_workspace(tmp_path)
    session = InteractiveSession(root)

    session.run_once("/start")

    text = (root / "work/discussion/research_script_draft.md").read_text(encoding="utf-8")
    assert "Data Availability" in text
    assert "contest_data" in text


def test_research_script_includes_llm_analysis(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text(
        "Estimate hidden fan votes for DWTS.", encoding="utf-8"
    )

    script = build_initial_research_script(root, language="zh", llm=_AnalysisLLM())

    assert "贝叶斯反演" in script.analysis
    assert "约束最优化" in script.analysis


def test_research_script_falls_back_when_llm_missing(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text("Problem.", encoding="utf-8")

    script = build_initial_research_script(root, language="en", llm=None)

    assert script.analysis == ""  # graceful: no analysis, but a valid script
    assert script.goals  # static goals still present


def test_research_script_falls_back_when_llm_raises(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text("Problem.", encoding="utf-8")

    script = build_initial_research_script(root, language="en", llm=_BrokenLLM())

    assert script.analysis == ""  # LLM failure must not crash /start
