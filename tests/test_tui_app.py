from pathlib import Path

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mcm_agent.core.workspace import create_workspace
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.tui.app import PromptUI


def test_promptui_dispatches_input_to_run_once(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    seen: list[str] = []
    orig = session.run_once
    session.run_once = lambda text: seen.append(text) or orig(text)  # type: ignore

    with create_pipe_input() as inp:
        inp.send_text("!echo hi\n")  # one command
        inp.send_text("\x04")        # Ctrl-D -> EOF -> exit loop
        PromptUI(session, input=inp, output=DummyOutput()).loop()

    assert "!echo hi" in seen
