from __future__ import annotations

from pathlib import Path

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _next_steps(state: object, settings: object) -> list[tuple[str, str]]:
    init = getattr(state, "init", None)
    llm_ok = bool(getattr(settings, "openai_api_key", ""))
    problem_ok = bool(getattr(init, "problem_imported", False))
    if not llm_ok:
        return [("/api", "配置 LLM API"), ("直接打字", "与我讨论建模方向")]
    if not problem_ok:
        return [("/question", "导入题目"), ("直接打字", "与我讨论建模方向")]
    return [
        ("/start", "分析题目并开始讨论"),
        ("直接打字", "与我讨论建模方向"),
        ("/api", "查看 / 配置 API"),
    ]


def render_welcome_panel(state: object, settings: object, version: str, cwd: Path) -> Panel:
    llm = getattr(settings, "openai_model", "") if getattr(settings, "openai_api_key", "") else "未配置 · 运行 /api"
    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="dim", justify="left")
    facts.add_column()
    facts.add_row("LLM", llm)
    facts.add_row("Workspace", Path(cwd).name)
    facts.add_row("Phase", Text(str(getattr(state, "phase", "")), style="accent.bright"))
    facts.add_row("cwd", str(cwd))

    steps = Text()
    steps.append("下一步\n", style="dim")
    for cmd, desc in _next_steps(state, settings):
        steps.append(f"  {cmd}", style="accent.bright")
        steps.append(f"   {desc}\n")

    header = Text()
    header.append("∑ ", style="accent")
    header.append("Mag", style="accent.bright")
    header.append("  MCM/ICM Modeling Agent", style="dim")

    body = Group(header, Text(""), facts, Text(""), steps)
    return Panel(
        body,
        box=box.ROUNDED,
        border_style="accent",
        title=f"∑ Mag  v{version}",
        title_align="left",
        padding=(1, 2),
    )
