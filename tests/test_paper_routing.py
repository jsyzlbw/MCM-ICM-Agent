"""TDD tests for paper-generation routing UX bug.

Bug: when user asks "write the paper" in chat, the LLM dumps a full markdown paper.
Fix: system prompt should instruct Mag to route such requests to /start --lock --run,
     and the --run result should explicitly name the deliverable paths.
"""
from __future__ import annotations

from pathlib import Path

from mcm_agent.cli_commands.base import CommandContext
from mcm_agent.cli_commands.start import StartCommand
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core import chat
from mcm_agent.core.workspace import create_workspace


def test_system_prompt_routes_paper_requests_to_pipeline(tmp_path: Path) -> None:
    """_SYSTEM must tell Mag to redirect paper/PDF requests to /start --lock --run."""
    assert "/start --lock --run" in chat._SYSTEM, (
        "_SYSTEM prompt does not mention '/start --lock --run'; "
        "the LLM will happily dump a full paper instead of routing the user."
    )


def test_start_run_reports_artifact_paths(tmp_path: Path) -> None:
    """--run result must name LaTeX source and PDF so user knows where to find them."""
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

    assert "main.tex" in result.message, (
        f"result.message does not mention 'main.tex': {result.message!r}"
    )
    assert "main.pdf" in result.message, (
        f"result.message does not mention 'main.pdf': {result.message!r}"
    )
