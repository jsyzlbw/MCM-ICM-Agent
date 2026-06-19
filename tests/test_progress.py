from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext
from mcm_agent.cli_commands.start import StartCommand
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_start_run_emits_human_readable_progress(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    problem = tmp_path / "p.md"
    problem.write_text("# Problem\nEstimate fan votes.", encoding="utf-8")
    data = tmp_path / "d.csv"
    data.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    session = InteractiveSession(root)
    session.run_once(f"/question {problem}")
    session.run_once(f"/data {data}")
    session.run_once("/init --llm-key test-key")
    env = root / ".env"
    env.write_text(env.read_text(encoding="utf-8") + "MAG_LLM_PROVIDER=fake\n", encoding="utf-8")

    labels: list[str] = []
    context = CommandContext(workspace_root=root, printer=labels.append)
    result = StartCommand().run(["--lock", "--run"], context)

    assert "workflow completed" in result.message
    assert any("撰写论文" in label for label in labels)
    assert any("理解题目" in label for label in labels)
