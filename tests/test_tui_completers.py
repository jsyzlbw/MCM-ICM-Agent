from prompt_toolkit.document import Document

from mcm_agent.tui.completers import SlashCommandCompleter


class _Cmd:
    def __init__(self, summary: str) -> None:
        self.summary = summary


def _texts(completer, text: str) -> list[str]:
    doc = Document(text, cursor_position=len(text))
    return [c.text for c in completer.get_completions(doc, None)]


def test_slash_completer_filters_by_prefix() -> None:
    comp = SlashCommandCompleter({"start": _Cmd("分析"), "status": _Cmd("状态"), "api": _Cmd("配置")})
    assert _texts(comp, "/st") == ["start", "status"]


def test_slash_completer_empty_slash_lists_all() -> None:
    comp = SlashCommandCompleter({"start": _Cmd("分析"), "api": _Cmd("配置")})
    assert set(_texts(comp, "/")) == {"start", "api"}


def test_slash_completer_inactive_without_leading_slash() -> None:
    comp = SlashCommandCompleter({"start": _Cmd("分析")})
    assert _texts(comp, "hello") == []
