"""TDD tests for TUI-2: / command-completion dropdown + input mode badge.

Tests are written FIRST and must fail before implementation.

Order of test logic:
1. Slash dropdown mounts when "/" is typed.
2. Filtering works (query "st" returns items matching "st").
3. Tab/Enter on dropdown fills the input with "/{name} " and removes popup.
4. Esc dismisses the popup.
5. Mode badge updates based on first character of input.
6. Regression: ask-bridge (ask-mode) still delivers answer when popup is open.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


from mcm_agent.cli_commands.base import CommandResult
from mcm_agent.core.workspace import create_workspace
from mcm_agent.cli_session import InteractiveSession
from mcm_agent.tui.textual_app import MagTuiApp, ChatTextArea, SlashCompleteWidget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(tmp_path: Path) -> InteractiveSession:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    session.run_once = lambda text: CommandResult("ok")  # type: ignore[method-assign]
    return session


def _popup(pilot) -> SlashCompleteWidget | None:
    """Return mounted SlashCompleteWidget or None."""
    try:
        return pilot.app.query_one(SlashCompleteWidget)
    except Exception:
        return None


def _popup_text(pilot) -> str:
    """Return the rendered text of the popup widget."""
    pw = _popup(pilot)
    if pw is None:
        return ""
    # Fallback: use render_str if available
    return str(pw.render()) if hasattr(pw, "render") else str(pw._renderable)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Test 1: Popup mounts when "/" typed
# ---------------------------------------------------------------------------


def test_slash_mounts_popup(tmp_path: Path) -> None:
    """Typing '/' into the prompt should mount a SlashCompleteWidget."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/")
            await pilot.pause(0.2)
            return _popup(pilot) is not None

    assert asyncio.run(_run()), "SlashCompleteWidget should be mounted after typing '/'"


# ---------------------------------------------------------------------------
# Test 2: Filtering — query "st" returns start/status items
# ---------------------------------------------------------------------------


def test_slash_filtered_by_query(tmp_path: Path) -> None:
    """Typing '/st' should show a popup whose filtered items include 'start' or 'status'."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/st")
            await pilot.pause(0.2)
            popup = _popup(pilot)
            if popup is None:
                return False, []
            # _filtered is the internal list after set_query
            filtered_names = [n for n, _ in popup._filtered]
            return True, filtered_names

    mounted, names = asyncio.run(_run())
    assert mounted, "SlashCompleteWidget should be mounted"
    assert any("st" in n.lower() for n in names), (
        f"Filtered items should contain names with 'st'; got: {names}"
    )


# ---------------------------------------------------------------------------
# Test 3: Tab selects item → input becomes "/{name} " → popup removed
# ---------------------------------------------------------------------------


def test_tab_selects_command_fills_input(tmp_path: Path) -> None:
    """Pressing Tab when popup is open selects current item and fills input."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/")
            await pilot.pause(0.2)
            popup = _popup(pilot)
            assert popup is not None, "Popup should be mounted before Tab"
            # Record what the first item name would be
            first_name = popup._filtered[0][0] if popup._filtered else None
            await pilot.press("tab")
            await pilot.pause(0.2)
            text_after = prompt.text
            popup_after = _popup(pilot)
            return text_after, popup_after, first_name

    text_after, popup_after, first_name = asyncio.run(_run())
    assert popup_after is None, "Popup should be removed after Tab"
    assert first_name is not None, "There should be at least one item"
    assert text_after == f"/{first_name} ", (
        f"Input should be '/{first_name} ' but got {text_after!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: Enter selects item → input becomes "/{name} " → popup removed
# ---------------------------------------------------------------------------


def test_enter_selects_command_fills_input(tmp_path: Path) -> None:
    """Pressing Enter when popup is open selects current item and fills input."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/")
            await pilot.pause(0.2)
            popup = _popup(pilot)
            assert popup is not None
            first_name = popup._filtered[0][0] if popup._filtered else None
            await pilot.press("enter")
            await pilot.pause(0.2)
            text_after = prompt.text
            popup_after = _popup(pilot)
            return text_after, popup_after, first_name

    text_after, popup_after, first_name = asyncio.run(_run())
    assert popup_after is None, "Popup should be removed after Enter"
    assert first_name is not None
    assert text_after == f"/{first_name} ", (
        f"Input should be '/{first_name} ' but got {text_after!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: Esc dismisses popup without filling input
# ---------------------------------------------------------------------------


def test_esc_dismisses_popup(tmp_path: Path) -> None:
    """Pressing Esc should remove the popup and leave the input as-is."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/help")
            await pilot.pause(0.2)
            assert _popup(pilot) is not None, "Popup should exist before Esc"
            await pilot.press("escape")
            await pilot.pause(0.2)
            return _popup(pilot), prompt.text

    popup_after, text = asyncio.run(_run())
    assert popup_after is None, "Popup should be dismissed after Esc"
    # Input text should still be "/help" (not cleared)
    assert text == "/help", f"Input should still be '/help' after Esc, got {text!r}"


# ---------------------------------------------------------------------------
# Test 6: Mode badge — "!" → "shell", "/" → "命令", plain → "讨论"
# ---------------------------------------------------------------------------


def _get_border_title(pilot) -> str:
    prompt = pilot.app.query_one("#prompt", ChatTextArea)
    return getattr(prompt, "border_title", "") or ""


def test_mode_badge_shell(tmp_path: Path) -> None:
    """Typing '!ls' should set the border_title badge to 'shell'."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("!ls")
            await pilot.pause(0.1)
            return _get_border_title(pilot)

    title = asyncio.run(_run())
    assert "shell" in title, f"Mode badge should show 'shell' when input starts with '!'; got {title!r}"


def test_mode_badge_command(tmp_path: Path) -> None:
    """Typing '/x' should set the border_title badge to '命令'."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("/x")
            await pilot.pause(0.1)
            return _get_border_title(pilot)

    title = asyncio.run(_run())
    assert "命令" in title, f"Mode badge should show '命令' when input starts with '/'; got {title!r}"


def test_mode_badge_discuss(tmp_path: Path) -> None:
    """Typing plain text should set the border_title badge to '讨论'."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("hello world")
            await pilot.pause(0.1)
            return _get_border_title(pilot)

    title = asyncio.run(_run())
    assert "讨论" in title, f"Mode badge should show '讨论' for plain text; got {title!r}"


def test_mode_badge_file(tmp_path: Path) -> None:
    """Typing '@foo' should set the border_title badge to '文件'."""
    session = _make_session(tmp_path)

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            prompt.insert("@foo")
            await pilot.pause(0.1)
            return _get_border_title(pilot)

    title = asyncio.run(_run())
    assert "文件" in title, f"Mode badge should show '文件' when input starts with '@'; got {title!r}"


# ---------------------------------------------------------------------------
# Test 7: Regression — ask-bridge still works with popup code present
# ---------------------------------------------------------------------------


def test_ask_mode_still_delivers_answer(tmp_path: Path) -> None:
    """In ask mode, Enter should still deliver the answer to the worker."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    answer_received: list[str] = []

    def fake_run_once(text: str) -> CommandResult:
        # Simulate a command that uses ctx.ask via the bridge
        answer = session._io_ask("What is your name?")  # type: ignore[misc]
        answer_received.append(answer)
        return CommandResult("done")

    session.run_once = fake_run_once  # type: ignore[method-assign]

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            # Use plain text (no slash) so no popup intercepts Enter
            prompt.insert("start task")
            await pilot.press("enter")
            # Wait for ask mode to be entered (worker calls _io_ask)
            await pilot.pause(0.5)
            # Now in ask mode: type the answer (plain text) and press enter
            prompt2 = pilot.app.query_one("#prompt", ChatTextArea)
            prompt2.insert("Alice")
            await pilot.press("enter")
            await pilot.pause(0.5)
            return answer_received

    received = asyncio.run(asyncio.wait_for(_run(), timeout=10.0))
    assert received == ["Alice"], f"Ask-bridge should deliver 'Alice', got {received!r}"


# ---------------------------------------------------------------------------
# Test 8: Popup not shown in ask mode (or if shown, Enter still delivers)
# ---------------------------------------------------------------------------


def test_ask_mode_enter_delivers_even_if_slash(tmp_path: Path) -> None:
    """In ask mode, typing '/a' should NOT show popup (ask mode suppresses it)
    and Enter should deliver '/a' as the answer to the worker."""
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    answer_received: list[str] = []

    def fake_run_once(text: str) -> CommandResult:
        answer = session._io_ask("Choose:")  # type: ignore[misc]
        answer_received.append(answer)
        return CommandResult("done")

    session.run_once = fake_run_once  # type: ignore[method-assign]

    async def _run():
        async with MagTuiApp(session).run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            prompt = pilot.app.query_one("#prompt", ChatTextArea)
            # Submit via plain text to avoid popup intercepting Enter
            prompt.insert("run something")
            await pilot.press("enter")
            await pilot.pause(0.5)
            # In ask mode: type "/a" (starts with slash)
            prompt2 = pilot.app.query_one("#prompt", ChatTextArea)
            prompt2.insert("/a")
            await pilot.pause(0.2)
            # Since we're in ask mode, popup should NOT appear
            popup_in_ask = _popup(pilot)
            # Enter should deliver "/a" as the answer (ask mode takes priority)
            await pilot.press("enter")
            await pilot.pause(0.5)
            return answer_received, popup_in_ask

    received, popup_in_ask = asyncio.run(asyncio.wait_for(_run(), timeout=10.0))
    assert popup_in_ask is None, "Popup should not appear in ask mode"
    assert received == ["/a"], f"In ask mode, Enter should deliver '/a', got {received!r}"
