from pathlib import Path

from prompt_toolkit.document import Document

from mcm_agent.tui.completers import AtFileCompleter, MagCompleter, SlashCommandCompleter


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


def test_at_completer_lists_workspace_files(tmp_path: Path) -> None:
    (tmp_path / "input" / "problem").mkdir(parents=True)
    (tmp_path / "input" / "problem" / "p.pdf").write_text("x", encoding="utf-8")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "junk.txt").write_text("x", encoding="utf-8")
    comp = AtFileCompleter(tmp_path)

    out = _texts(comp, "@in")  # _texts defined earlier in this file

    assert any("input/problem/p.pdf" in t for t in out)
    assert all("work/junk.txt" not in t for t in out)  # work/ ignored


def test_mag_completer_dispatches_by_prefix(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text("x", encoding="utf-8")
    comp = MagCompleter({"start": _Cmd("分析")}, tmp_path)  # _Cmd defined earlier
    assert _texts(comp, "/st") == ["start"]
    assert any("data.csv" in t for t in _texts(comp, "@da"))
