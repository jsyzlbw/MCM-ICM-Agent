from __future__ import annotations

from prompt_toolkit.key_binding import KeyBindings


def build_key_bindings() -> KeyBindings:
    kb = KeyBindings()
    state = {"ctrl_c": 0}

    @kb.add("escape", "enter")  # Alt/Option+Enter inserts a newline (multiline input)
    def _(event) -> None:
        event.current_buffer.insert_text("\n")

    @kb.add("c-c")
    def _(event) -> None:
        buf = event.current_buffer
        if buf.text:
            buf.reset()  # first Ctrl+C on a non-empty line: just clear it
            state["ctrl_c"] = 0
            return
        state["ctrl_c"] += 1
        if state["ctrl_c"] >= 2:
            event.app.exit(exception=EOFError)  # second Ctrl+C on empty line: quit
        else:
            # surface a hint via the app's output
            event.app.output.write("\n(再按一次 Ctrl+C 退出)\n")
            event.app.output.flush()

    return kb
