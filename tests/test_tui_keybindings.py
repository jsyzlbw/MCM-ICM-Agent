from prompt_toolkit.key_binding import KeyBindings

from mcm_agent.tui.keybindings import build_key_bindings


def test_build_key_bindings_registers_bindings() -> None:
    kb = build_key_bindings()
    assert isinstance(kb, KeyBindings)
    assert len(kb.bindings) >= 2  # at least Alt+Enter newline and Ctrl+C
