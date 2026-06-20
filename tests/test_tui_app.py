from pathlib import Path

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

import mcm_agent.tui.app as app_mod
from mcm_agent.core.workspace import create_workspace
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.tui.app import PromptUI


def test_toolbar_caches_expensive_loads(tmp_path: Path, monkeypatch) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    ui = PromptUI(session)

    state_calls: list[int] = []
    settings_calls: list[int] = []
    real_state = app_mod.load_workspace_state
    real_settings = app_mod.load_settings
    monkeypatch.setattr(
        app_mod, "load_workspace_state", lambda r: (state_calls.append(1), real_state(r))[1]
    )
    monkeypatch.setattr(
        app_mod, "load_settings", lambda **k: (settings_calls.append(1), real_settings(**k))[1]
    )

    first = ui._toolbar()
    ui._toolbar()
    ui._toolbar()
    assert len(state_calls) == 1  # cached across keystrokes
    assert len(settings_calls) == 1

    ui._invalidate_caches()
    assert ui._toolbar() == first  # same workspace -> same rendering
    assert len(state_calls) == 2  # invalidation forces a fresh load
    assert len(settings_calls) == 2


def test_loop_invalidates_caches_after_each_command(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    with create_pipe_input() as inp:
        ui = PromptUI(session, input=inp, output=DummyOutput())
        calls: list[int] = []
        ui._invalidate_caches = lambda: calls.append(1)  # type: ignore[method-assign]
        inp.send_text("!echo hi\n")  # one command
        inp.send_text("\x04")        # Ctrl-D -> EOF -> exit loop
        ui.loop()

    assert len(calls) == 1  # invalidated once, for the single command


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
