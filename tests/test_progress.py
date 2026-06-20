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

    context = CommandContext(workspace_root=root, printer=lambda _: None)
    result = StartCommand().run(["--lock", "--run"], context)

    assert "main.tex" in result.message or "已完成" in result.message


def test_workflow_emits_per_stage_progress_labels(tmp_path: Path) -> None:
    from mcm_agent.core.workflow_adapter import WorkspaceWorkflowAdapter

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
    session.run_once("/start --lock")

    seen: list[str] = []
    WorkspaceWorkflowAdapter(root).run_default_workflow(auto_approve=True, progress=seen.append)

    assert seen, "no progress labels emitted"
    assert any("正在" in str(label) for label in seen)
