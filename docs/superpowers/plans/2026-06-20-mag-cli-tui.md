# Mag CLI — Claude-Code 风格 TUI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `mag` 交互式 shell 升级为模仿 Claude Code 的优雅终端 UI：欢迎面板、`/` 命令补全、`@` 文件引用、`!` shell、底部状态行、历史/多行、可中断进度。

**Architecture:** 新增 `src/mcm_agent/tui/` 展示层（theme/welcome/completers/keybindings/statusbar/runner/app）与 `core/shell_exec.py`；`InteractiveSession.run_once` 维持唯一逻辑入口不变，仅在 `run()` 按 TTY 分流：TTY → prompt_toolkit 驱动的 `PromptUI`，非 TTY → 原 `console.input` 纯循环（保护 497 个既有测试）。prompt_toolkit 只「拥有输入」，rich 仍是唯一渲染器。

**Tech Stack:** Python 3.12+，prompt_toolkit（输入/补全/历史/键位）、rich（面板/主题/markdown）、subprocess（`!`）、threading + rich.Live（spinner）。

参考设计文档：`docs/superpowers/specs/2026-06-20-mag-cli-tui-design.md`。

## Global Constraints

- 新增显式依赖：`prompt_toolkit>=3.0.50`（已随 questionary 安装 3.0.52；显式声明解耦）。无其它新依赖。
- 特征色 = **建模青 teal**（`accent=#1D9E75`，亮 `#5DCAA5`；`success=#639922` 黄绿避免与 teal 混；`warning=#EF9F27`；`error=#E24B4A`）。品牌符号 = `∑`。**不得**用 Claude 的珊瑚橙 / `✻`。
- `run_once(text)` 是唯一逻辑入口；`/`、`@`、纯文本都经它；`!` 作为 run_once 的特例分支（不进命令注册表、不需 TTY，便于测试）。
- 主题只作用于「界面外壳」（面板/提示符/状态栏/补全/spinner/错误前缀）；命令正文 `_print` 继续 `markup=False, highlight=False`（保 `[ok]` 等字面标记）。
- **非 TTY 必须降级**到原 `console.input` 纯循环；pt 导入失败也降级。pytest `CliRunner`/管道/CI 路径零改。
- TDD：每个代码步骤先写失败测试；频繁提交；每阶段同步 main。
- 所有新单测离线、无网络。涉及 LLM 的测试用 fake provider。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `src/mcm_agent/version.py` (新) | 单一版本号来源 `__version__`，供 cli.py 与面板共用，避免循环导入 |
| `src/mcm_agent/core/shell_exec.py` (新) | `run_shell(root, cmd)` → `ShellResult`，`!` 透传执行 |
| `src/mcm_agent/tui/__init__.py` (新) | 包标记 |
| `src/mcm_agent/tui/theme.py` (新) | `MAG_THEME`(rich.Theme) + 颜色常量 + `BOTTOM_HINT` |
| `src/mcm_agent/tui/welcome.py` (新) | `render_welcome_panel(state, settings, version, cwd)` → rich.Panel |
| `src/mcm_agent/tui/completers.py` (新) | `SlashCommandCompleter`、`AtFileCompleter`、`MagCompleter` |
| `src/mcm_agent/tui/statusbar.py` (新) | `bottom_toolbar(state, settings)` → str |
| `src/mcm_agent/tui/keybindings.py` (新) | `build_key_bindings()` → pt KeyBindings（Ctrl+C×2、Alt+Enter 换行） |
| `src/mcm_agent/tui/runner.py` (新) | `run_with_spinner(fn, verb)`：线程阻塞 + rich.Live spinner + 可中断 |
| `src/mcm_agent/tui/app.py` (新) | `PromptUI(session).loop()`：pt 输入循环，驱动 `run_once` |
| `src/mcm_agent/cli_session.py` (改) | `run()` TTY 分流；`_run_plain()`；`_print_welcome()`；`!` 分支；`@` 注入；themed console |
| `src/mcm_agent/cli.py` (改) | `VERSION` 改为引用 `version.__version__` |
| `src/mcm_agent/core/chat.py` (改) | `generate_chat_reply(..., attachments=None)` 注入 `@` 文件 |
| `src/mcm_agent/providers/llm.py` (改, P4) | `generate_stream` 流式 |
| `pyproject.toml` (改) | 加 `prompt_toolkit>=3.0.50` |
| `tests/test_shell_exec.py` … (新) | 各单元测试 |

---

# Phase 1 — 外壳与基础（无 prompt_toolkit，低风险先出观感）

### Task 1: shell 执行器 `core/shell_exec.py`

**Files:**
- Create: `src/mcm_agent/core/shell_exec.py`
- Test: `tests/test_shell_exec.py`

**Interfaces:**
- Produces: `ShellResult(exit_code: int, stdout: str, stderr: str)`；`run_shell(workspace_root: Path, command: str, *, timeout_seconds: int = 120) -> ShellResult`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_shell_exec.py
from pathlib import Path

from mcm_agent.core.shell_exec import ShellResult, run_shell


def test_run_shell_captures_stdout_and_exit_zero(tmp_path: Path) -> None:
    result = run_shell(tmp_path, "echo hello")
    assert isinstance(result, ShellResult)
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_run_shell_reports_nonzero_exit(tmp_path: Path) -> None:
    result = run_shell(tmp_path, "exit 3")
    assert result.exit_code == 3


def test_run_shell_runs_in_workspace_cwd(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    result = run_shell(tmp_path, "ls")
    assert "marker.txt" in result.stdout


def test_run_shell_times_out(tmp_path: Path) -> None:
    result = run_shell(tmp_path, "sleep 5", timeout_seconds=1)
    assert result.exit_code == 124
    assert "timed out" in result.stderr.lower()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_shell_exec.py -q`
Expected: FAIL（ModuleNotFoundError: mcm_agent.core.shell_exec）

- [ ] **Step 3: 实现**

```python
# src/mcm_agent/core/shell_exec.py
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ShellResult:
    exit_code: int
    stdout: str
    stderr: str


def run_shell(
    workspace_root: Path, command: str, *, timeout_seconds: int = 120
) -> ShellResult:
    """Run a shell command in the workspace dir, capturing output. Never raises;
    a timeout returns exit_code 124 with a note appended to stderr."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return ShellResult(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as exc:
        def _decode(value: object) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", "replace")
            return value or ""

        return ShellResult(
            124,
            _decode(exc.stdout),
            _decode(exc.stderr) + f"\n[timed out after {timeout_seconds}s]",
        )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_shell_exec.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/core/shell_exec.py tests/test_shell_exec.py
git commit -m "feat(cli): shell_exec.run_shell for ! passthrough"
```

---

### Task 2: `!` 分支接入 `run_once`

**Files:**
- Modify: `src/mcm_agent/cli_session.py`（`run_once` 顶部加分支 + 新 `_run_shell` 方法）
- Test: `tests/test_shell_command.py`

**Interfaces:**
- Consumes: `run_shell` / `ShellResult`（Task 1）
- Produces: 输入以 `!` 开头时，`run_once` 返回含命令输出与 `(exit N)` 的 `CommandResult`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_shell_command.py
from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_bang_runs_shell_and_echoes_output(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("!echo hi")

    assert "hi" in result.message
    assert "(exit 0)" in result.message


def test_bang_nonzero_exit_shown(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("!exit 2")

    assert "(exit 2)" in result.message


def test_bang_empty_shows_usage(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("!")

    assert "用法" in result.message
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_shell_command.py -q`
Expected: FAIL（`!echo hi` 当前被当作自然语言，无 "(exit 0)"）

- [ ] **Step 3: 实现** — 在 `cli_session.py` 的 `run_once` 中，紧接 `self.session_store.append_message("user", stripped)`（第 61 行）之后、`if stripped == "/help":` 之前插入：

```python
        if stripped.startswith("!"):
            result = self._run_shell(stripped[1:].strip())
            if result.message:
                self.session_store.append_message("assistant", result.message)
            return result
```

并新增方法（放在 `_handle_natural_language` 附近）：

```python
    def _run_shell(self, command: str) -> CommandResult:
        if not command:
            return CommandResult("用法：!<shell 命令>，例如  !ls input/data")
        from mcm_agent.core.shell_exec import run_shell

        result = run_shell(self.workspace_root, command)
        lines: list[str] = []
        if result.stdout.strip():
            lines.append(result.stdout.rstrip())
        if result.stderr.strip():
            lines.append(result.stderr.rstrip())
        lines.append(f"(exit {result.exit_code})")
        return CommandResult("\n".join(lines))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_shell_command.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 回归 + 提交**

```bash
python -m pytest tests/test_chat.py tests/test_research_script.py -q
git add src/mcm_agent/cli_session.py tests/test_shell_command.py
git commit -m "feat(cli): ! prefix runs shell via run_once"
```

---

### Task 3: 单一版本号 `version.py`

**Files:**
- Create: `src/mcm_agent/version.py`
- Modify: `src/mcm_agent/cli.py`（`VERSION` 引用它）
- Test: `tests/test_version.py`

**Interfaces:**
- Produces: `mcm_agent.version.__version__ = "0.1.0"`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_version.py
def test_version_is_single_source() -> None:
    from mcm_agent.version import __version__

    assert __version__ == "0.1.0"

    import mcm_agent.cli as cli

    assert cli.VERSION == __version__
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_version.py -q`
Expected: FAIL（ModuleNotFoundError: mcm_agent.version）

- [ ] **Step 3: 实现**

```python
# src/mcm_agent/version.py
from __future__ import annotations

__version__ = "0.1.0"
```

在 `cli.py` 中把 `VERSION = "0.1.0"` 改为：

```python
from mcm_agent.version import __version__

VERSION = __version__
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_version.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/version.py src/mcm_agent/cli.py tests/test_version.py
git commit -m "refactor(cli): single-source version in version.py"
```

---

### Task 4: 主题 `tui/theme.py`

**Files:**
- Create: `src/mcm_agent/tui/__init__.py`（空）
- Create: `src/mcm_agent/tui/theme.py`
- Test: `tests/test_tui_theme.py`

**Interfaces:**
- Produces: `MAG_THEME: rich.theme.Theme`；常量 `ACCENT`、`ACCENT_BRIGHT`、`SUCCESS`、`WARNING`、`ERROR`；`BOTTOM_HINT: str`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tui_theme.py
def test_theme_uses_teal_accent_not_coral() -> None:
    from mcm_agent.tui.theme import ACCENT, MAG_THEME

    assert ACCENT == "#1D9E75"  # teal, not Claude coral
    assert "accent" in MAG_THEME.styles


def test_bottom_hint_lists_modes() -> None:
    from mcm_agent.tui.theme import BOTTOM_HINT

    for token in ("/help", "/ 菜单", "! shell", "@ 文件"):
        assert token in BOTTOM_HINT
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_theme.py -q`
Expected: FAIL（ModuleNotFoundError: mcm_agent.tui.theme）

- [ ] **Step 3: 实现**

```python
# src/mcm_agent/tui/__init__.py
```

```python
# src/mcm_agent/tui/theme.py
from __future__ import annotations

from rich.theme import Theme

# 建模青 (teal) signature palette — see spec §13.1. Deliberately NOT Claude's coral.
ACCENT = "#1D9E75"         # teal-400: brand, panel border, prompt, highlight
ACCENT_BRIGHT = "#5DCAA5"  # teal-200: emphasis text on dark terminals
SUCCESS = "#639922"        # yellow-green: distinct from the teal accent
WARNING = "#EF9F27"
ERROR = "#E24B4A"

MAG_THEME = Theme(
    {
        "accent": ACCENT,
        "accent.bright": ACCENT_BRIGHT,
        "success": SUCCESS,
        "warning": WARNING,
        "error": ERROR,
    }
)

BOTTOM_HINT = "/help 命令 · / 菜单 · ! shell · @ 文件 · ? 快捷键"
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_theme.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/tui/__init__.py src/mcm_agent/tui/theme.py tests/test_tui_theme.py
git commit -m "feat(tui): teal signature theme + bottom hint"
```

---

### Task 5: 欢迎面板 `tui/welcome.py` + 接入启动

**Files:**
- Create: `src/mcm_agent/tui/welcome.py`
- Modify: `src/mcm_agent/cli_session.py`（`__init__` 用 themed console；`run()` → `_print_welcome()` + `_run_plain()`）
- Test: `tests/test_tui_welcome.py`

**Interfaces:**
- Consumes: `MAG_THEME`、`ACCENT`（Task 4）；`version.__version__`（Task 3）；`load_workspace_state`、`load_settings`
- Produces: `render_welcome_panel(state, settings, version: str, cwd: Path) -> rich.panel.Panel`；`InteractiveSession._print_welcome()`、`._run_plain()`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tui_welcome.py
from pathlib import Path

from rich.console import Console

from mcm_agent.config import load_settings
from mcm_agent.core.workspace import create_workspace, load_workspace_state
from mcm_agent.tui.theme import MAG_THEME
from mcm_agent.tui.welcome import render_welcome_panel


def _render(panel) -> str:
    console = Console(theme=MAG_THEME, width=80, file=None)
    with console.capture() as cap:
        console.print(panel)
    return cap.get()


def test_welcome_panel_shows_brand_and_next_step(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    out = _render(render_welcome_panel(state, settings, "0.1.0", root))

    assert "Mag" in out
    assert "∑" in out          # math brand glyph, not ✻
    assert "0.1.0" in out
    assert "Workspace" in out
    assert "/init" in out or "/api" in out  # next-step for a fresh workspace


def test_welcome_panel_shows_llm_when_configured(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    from mcm_agent.core.config_writer import set_env_var

    set_env_var(root, "MAG_LLM_API_KEY", "sk-x")
    set_env_var(root, "MAG_LLM_MODEL", "deepseek-v4-flash")
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    out = _render(render_welcome_panel(state, settings, "0.1.0", root))

    assert "deepseek-v4-flash" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_welcome.py -q`
Expected: FAIL（ModuleNotFoundError: mcm_agent.tui.welcome）

- [ ] **Step 3: 实现 welcome.py**

```python
# src/mcm_agent/tui/welcome.py
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_welcome.py -q`
Expected: PASS

- [ ] **Step 5: 接入 cli_session** — 改 `__init__` 的 console，并把 `run()` 拆出 `_run_plain` + `_print_welcome`：

`__init__` 中：

```python
        from mcm_agent.tui.theme import MAG_THEME

        self.console = console or Console(theme=MAG_THEME)
```

把现有 `run()`（第 117-129 行）整体替换为：

```python
    def run(self) -> None:
        self._run_plain()

    def _print_welcome(self) -> None:
        from mcm_agent.config import load_settings
        from mcm_agent.tui.theme import BOTTOM_HINT
        from mcm_agent.tui.welcome import render_welcome_panel
        from mcm_agent.version import __version__

        state = load_workspace_state(self.workspace_root)
        settings = load_settings(workspace_root=self.workspace_root)
        self.console.print(render_welcome_panel(state, settings, __version__, self.workspace_root))
        self.console.print(BOTTOM_HINT, style="dim")

    def _run_plain(self) -> None:
        self._print_welcome()
        while True:
            try:
                text = self.console.input("> ", markup=False)
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                return
            result = self.run_once(text)
            if result.message:
                self._print(result.message)
            if result.exit_session:
                return
```

- [ ] **Step 6: 回归 + 手测 + 提交**

```bash
python -m pytest -q
```
Expected: 全绿（新增测试 + 既有 497）。手测：在空目录 `mag`，应见 teal 圆角欢迎面板 + 底部提示行。

```bash
git add src/mcm_agent/tui/welcome.py src/mcm_agent/cli_session.py tests/test_tui_welcome.py
git commit -m "feat(tui): teal welcome panel at startup"
```

> **Phase 1 完成：推送 main。** `git push origin main`

---

# Phase 2 — prompt_toolkit 输入循环（核心交互）

### Task 6: 声明 prompt_toolkit 依赖

**Files:**
- Modify: `pyproject.toml`（`[project].dependencies` 加一行）

- [ ] **Step 1: 修改** — 在 `dependencies` 列表中 `"questionary>=2.0.1",` 之后加：

```toml
  "prompt_toolkit>=3.0.50",
```

- [ ] **Step 2: 确认可导入**

Run: `python -c "import prompt_toolkit; print(prompt_toolkit.__version__)"`
Expected: 打印 `3.0.5x`（已随 questionary 安装）

- [ ] **Step 3: 提交**

```bash
git add pyproject.toml
git commit -m "build: declare prompt_toolkit dependency"
```

---

### Task 7: 斜杠补全 `tui/completers.py`（SlashCommandCompleter）

**Files:**
- Create: `src/mcm_agent/tui/completers.py`
- Test: `tests/test_tui_completers.py`

**Interfaces:**
- Produces: `SlashCommandCompleter(commands: dict[str, object])`，`commands` 值需有 `.summary` 属性

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tui_completers.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_completers.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/mcm_agent/tui/completers.py
from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion


class SlashCommandCompleter(Completer):
    """Completes '/<name>' from the command registry, showing each summary."""

    def __init__(self, commands: dict[str, object]) -> None:
        self._commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        word = text[1:]
        for name in sorted(self._commands):
            if name.startswith(word):
                summary = getattr(self._commands[name], "summary", "")
                yield Completion(
                    name,
                    start_position=-len(word),
                    display=f"/{name}",
                    display_meta=summary,
                )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_completers.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/tui/completers.py tests/test_tui_completers.py
git commit -m "feat(tui): slash-command completer"
```

---

### Task 8: 底部状态行 `tui/statusbar.py`

**Files:**
- Create: `src/mcm_agent/tui/statusbar.py`
- Test: `tests/test_tui_statusbar.py`

**Interfaces:**
- Produces: `bottom_toolbar(state, settings) -> str`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tui_statusbar.py
from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.core.workspace import create_workspace, load_workspace_state
from mcm_agent.tui.statusbar import bottom_toolbar


def test_toolbar_shows_llm_and_phase(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    from mcm_agent.core.config_writer import set_env_var

    set_env_var(root, "MAG_LLM_API_KEY", "sk-x")
    set_env_var(root, "MAG_LLM_MODEL", "deepseek-v4-flash")
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    text = bottom_toolbar(state, settings)

    assert "deepseek-v4-flash" in text
    assert str(state.phase) in text


def test_toolbar_unconfigured_llm(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    state = load_workspace_state(root)
    settings = load_settings(workspace_root=root)

    assert "未配置" in bottom_toolbar(state, settings)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_statusbar.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/mcm_agent/tui/statusbar.py
from __future__ import annotations


def bottom_toolbar(state: object, settings: object) -> str:
    llm = getattr(settings, "openai_model", "") if getattr(settings, "openai_api_key", "") else "未配置"
    phase = str(getattr(state, "phase", ""))
    return f" {llm} · {phase}    ? 快捷键 · ! shell · @ 文件 "
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_statusbar.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/tui/statusbar.py tests/test_tui_statusbar.py
git commit -m "feat(tui): bottom status toolbar"
```

---

### Task 9: 键位 `tui/keybindings.py`（Ctrl+C×2 退出 + Alt+Enter 换行）

**Files:**
- Create: `src/mcm_agent/tui/keybindings.py`
- Test: `tests/test_tui_keybindings.py`

**Interfaces:**
- Produces: `build_key_bindings() -> prompt_toolkit.key_binding.KeyBindings`（绑定：`escape,enter` 插入换行；`c-c` 第一次清行+提示、第二次抛 EOFError 退出）

- [ ] **Step 1: 写失败测试**（断言返回 KeyBindings 且注册了 ≥2 条；不内省具体键名以免跨版本脆弱）

```python
# tests/test_tui_keybindings.py
from prompt_toolkit.key_binding import KeyBindings

from mcm_agent.tui.keybindings import build_key_bindings


def test_build_key_bindings_registers_bindings() -> None:
    kb = build_key_bindings()
    assert isinstance(kb, KeyBindings)
    assert len(kb.bindings) >= 2  # at least Alt+Enter newline and Ctrl+C
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_keybindings.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/mcm_agent/tui/keybindings.py
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
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_keybindings.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/tui/keybindings.py tests/test_tui_keybindings.py
git commit -m "feat(tui): key bindings (alt+enter newline, ctrl+c twice to quit)"
```

---

### Task 10: `PromptUI` + `run()` TTY 分流

**Files:**
- Create: `src/mcm_agent/tui/app.py`
- Modify: `src/mcm_agent/cli_session.py`（`run()` 改为 TTY 分流）
- Test: `tests/test_tui_app.py`（pt 管道输入）；`tests/test_cli_tui_smoke.py`（pexpect pty，薄）

**Interfaces:**
- Consumes: `SlashCommandCompleter`（Task 7）、`bottom_toolbar`（Task 8）、`build_key_bindings`（Task 9）、`InteractiveSession.run_once/_print/_print_welcome`
- Produces: `PromptUI(session, *, input=None, output=None)`；`PromptUI.loop()`；`InteractiveSession.run()` 在 TTY 下走 `PromptUI`

- [ ] **Step 1: 写失败测试（pt 管道输入，无 TTY 也能测）**

```python
# tests/test_tui_app.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_app.py -q`
Expected: FAIL（ModuleNotFoundError: mcm_agent.tui.app）

- [ ] **Step 3: 实现 app.py**

```python
# src/mcm_agent/tui/app.py
from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from mcm_agent.config import load_settings
from mcm_agent.core.workspace import load_workspace_state
from mcm_agent.tui.completers import SlashCommandCompleter
from mcm_agent.tui.keybindings import build_key_bindings
from mcm_agent.tui.statusbar import bottom_toolbar
from mcm_agent.tui.theme import ACCENT

_PROMPT_STYLE = Style.from_dict({"prompt": f"{ACCENT} bold"})


class PromptUI:
    """prompt_toolkit input loop. Owns input only; rich still renders all output.
    run_once stays the single logic entry."""

    def __init__(self, session, *, input=None, output=None) -> None:
        self.session = session
        self._input = input
        self._output = output

    def _toolbar(self):
        state = load_workspace_state(self.session.workspace_root)
        settings = load_settings(workspace_root=self.session.workspace_root)
        return bottom_toolbar(state, settings)

    def loop(self) -> None:
        history_path = self.session.workspace_root / ".mag" / "history"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        ps = PromptSession(
            history=FileHistory(str(history_path)),
            completer=SlashCommandCompleter(self.session.commands),
            complete_while_typing=True,
            key_bindings=build_key_bindings(),
            bottom_toolbar=self._toolbar,
            input=self._input,
            output=self._output,
        )
        self.session._print_welcome()
        while True:
            try:
                with patch_stdout():
                    text = ps.prompt(HTML("<prompt>&gt; </prompt>"), style=_PROMPT_STYLE)
            except KeyboardInterrupt:
                continue
            except EOFError:
                return
            result = self.session.run_once(text)
            if result.message:
                self.session._print(result.message)
            if result.exit_session:
                return
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_app.py -q`
Expected: PASS

- [ ] **Step 5: 接入 `run()` 的 TTY 分流** — 把 Task 5 写的 `run()` 改为：

```python
    def run(self) -> None:
        import sys

        try:
            interactive = sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            interactive = False
        if not interactive:
            return self._run_plain()
        try:
            from mcm_agent.tui.app import PromptUI
        except ImportError:
            return self._run_plain()
        PromptUI(self).loop()
```

- [ ] **Step 6: pexpect 冒烟测试（薄）**

```python
# tests/test_cli_tui_smoke.py
import sys

import pytest

pexpect = pytest.importorskip("pexpect")


@pytest.mark.skipif(sys.platform == "win32", reason="pty not supported on Windows")
def test_mag_tui_starts_and_runs_shell(tmp_path):
    child = pexpect.spawn(
        sys.executable, ["-m", "mcm_agent.cli"], cwd=str(tmp_path),
        encoding="utf-8", timeout=30, dimensions=(40, 100),
    )
    child.expect_exact("> ")          # welcome panel rendered, prompt docked
    child.sendline("!echo smoke-ok")
    child.expect("smoke-ok")
    child.send("\x04")                # Ctrl-D quits
    child.expect(pexpect.EOF)
```

> 注：`python -m mcm_agent.cli` 需可用。若 `cli.py` 无 `__main__` 入口，新增文件末尾：`if __name__ == "__main__": app()`（仅此一行，纳入本步提交）。

- [ ] **Step 7: 运行确认通过**

Run: `python -m pytest tests/test_tui_app.py tests/test_cli_tui_smoke.py -q`
Expected: PASS

- [ ] **Step 8: 全量回归 + 提交 + 推送**

```bash
python -m pytest -q
git add src/mcm_agent/tui/app.py src/mcm_agent/cli_session.py src/mcm_agent/cli.py \
        tests/test_tui_app.py tests/test_cli_tui_smoke.py
git commit -m "feat(tui): prompt_toolkit input loop with slash completion, history, toolbar"
git push origin main
```

---

# Phase 3 — 文件引用与运行进度

### Task 11: `@` 文件补全 + `MagCompleter`

**Files:**
- Modify: `src/mcm_agent/tui/completers.py`（加 `AtFileCompleter`、`MagCompleter`）
- Modify: `src/mcm_agent/tui/app.py`（completer 换成 `MagCompleter`）
- Test: `tests/test_tui_completers.py`（追加）

**Interfaces:**
- Produces: `AtFileCompleter(workspace_root: Path)`；`MagCompleter(commands, workspace_root)`（按首字符分派 `/` 或 `@`）
- `AtFileCompleter` 忽略 `work/`、`output/`、`.git/`、`.mag/`、`node_modules/`、`__pycache__/`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_tui_completers.py
from pathlib import Path

from mcm_agent.tui.completers import AtFileCompleter, MagCompleter


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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_completers.py -q`
Expected: FAIL（ImportError: AtFileCompleter）

- [ ] **Step 3: 实现** — 在 `completers.py` 追加：

```python
from pathlib import Path

_IGNORE_DIRS = {"work", "output", ".git", ".mag", "node_modules", "__pycache__"}


class AtFileCompleter(Completer):
    """Completes '@<path>' with workspace files, skipping noise/output dirs."""

    def __init__(self, workspace_root: Path) -> None:
        self._root = Path(workspace_root)

    def _candidates(self) -> list[str]:
        out: list[str] = []
        for path in self._root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self._root)
            if any(part in _IGNORE_DIRS for part in rel.parts):
                continue
            out.append(rel.as_posix())
        return sorted(out)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        at = text.rfind("@")
        if at == -1:
            return
        word = text[at + 1 :]
        if " " in word:
            return
        for rel in self._candidates():
            if rel.startswith(word):
                yield Completion(rel, start_position=-len(word), display=f"@{rel}")


class MagCompleter(Completer):
    """Dispatch to slash or file completion by the active token's prefix."""

    def __init__(self, commands: dict[str, object], workspace_root: Path) -> None:
        self._slash = SlashCommandCompleter(commands)
        self._at = AtFileCompleter(workspace_root)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            yield from self._slash.get_completions(document, complete_event)
        elif "@" in text:
            yield from self._at.get_completions(document, complete_event)
```

在 `app.py` 中把 `completer=SlashCommandCompleter(self.session.commands)` 改为：

```python
            completer=MagCompleter(self.session.commands, self.session.workspace_root),
```
并更新 import（`from mcm_agent.tui.completers import MagCompleter`）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_completers.py tests/test_tui_app.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/tui/completers.py src/mcm_agent/tui/app.py tests/test_tui_completers.py
git commit -m "feat(tui): @ file completer + combined MagCompleter"
```

---

### Task 12: `@` 文件内容注入对话上下文

**Files:**
- Modify: `src/mcm_agent/core/chat.py`（`generate_chat_reply` 加 `attachments` 形参）
- Modify: `src/mcm_agent/cli_session.py`（`_handle_natural_language` 解析 `@token` → 传 attachments；新增 `_collect_attachments`）
- Test: `tests/test_chat.py`（追加）；`tests/test_at_injection.py`

**Interfaces:**
- Consumes: 既有 `generate_chat_reply(workspace_root, message, llm_provider, recent_messages)`
- Produces: `generate_chat_reply(..., attachments: list[tuple[str, str]] | None = None)`；`InteractiveSession._collect_attachments(text) -> list[tuple[str, str]]`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_chat.py
def test_chat_reply_includes_attachment_content(tmp_path) -> None:
    from pathlib import Path
    from mcm_agent.core.workspace import create_workspace

    root = create_workspace(Path(tmp_path) / "ws").root
    llm = _EchoLLM()

    generate_chat_reply(root, "看看 @data.csv", llm, [], attachments=[("data.csv", "a,b\n1,2")])

    assert "data.csv" in llm.last_prompt
    assert "a,b" in llm.last_prompt
```

```python
# tests/test_at_injection.py
from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_collect_attachments_reads_existing_workspace_file(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "notes.txt").write_text("hello-content", encoding="utf-8")
    session = InteractiveSession(root)

    atts = session._collect_attachments("解释 @notes.txt 里的内容")

    assert atts == [("notes.txt", "hello-content")]


def test_collect_attachments_ignores_missing(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    assert session._collect_attachments("看 @nope.txt") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_at_injection.py "tests/test_chat.py::test_chat_reply_includes_attachment_content" -q`
Expected: FAIL（`attachments` 参数不存在 / `_collect_attachments` 未定义）

- [ ] **Step 3: 实现 chat.py** — 改签名与 prompt 拼装：

```python
def generate_chat_reply(
    workspace_root: Path,
    message: str,
    llm_provider: object | None,
    recent_messages: list[dict[str, object]] | None,
    attachments: list[tuple[str, str]] | None = None,
) -> str:
```

在 prompt 组装的 `part for part in [...]` 列表里，`f"USER:\n{message}"` 之前插入附件段：

```python
            "\n\n".join(f"ATTACHED FILE {name}:\n{content}" for name, content in (attachments or [])),
```

- [ ] **Step 4: 实现 cli_session** — 在 `_handle_natural_language` 中把
`reply = generate_chat_reply(self.workspace_root, text, self._chat_llm(), recent)` 改为：

```python
        attachments = self._collect_attachments(text)
        reply = generate_chat_reply(
            self.workspace_root, text, self._chat_llm(), recent, attachments=attachments
        )
```

新增方法：

```python
    def _collect_attachments(self, text: str) -> list[tuple[str, str]]:
        import re

        out: list[tuple[str, str]] = []
        for token in re.findall(r"@(\S+)", text):
            path = self.workspace_root / token
            if path.is_file():
                try:
                    out.append((token, path.read_text(encoding="utf-8")[:4000]))
                except (UnicodeDecodeError, OSError):
                    out.append((token, "[binary or unreadable file]"))
        return out
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/test_at_injection.py tests/test_chat.py -q`
Expected: PASS（含既有 chat 测试）

- [ ] **Step 6: 提交**

```bash
git add src/mcm_agent/core/chat.py src/mcm_agent/cli_session.py tests/test_chat.py tests/test_at_injection.py
git commit -m "feat(tui): @ file references inject content into chat context"
```

---

### Task 13: 运行时 spinner `tui/runner.py` + 接入对话/工作流

**Files:**
- Create: `src/mcm_agent/tui/runner.py`
- Modify: `src/mcm_agent/cli_session.py`（chat 调用包 spinner；chat 回复用 markdown 渲染）
- Test: `tests/test_tui_runner.py`

**Interfaces:**
- Produces: `run_with_spinner(fn: Callable[[], T], verb: str, *, console=None) -> T`（同步执行 `fn`，运行时显示单行 spinner；返回 `fn()` 结果；异常透传）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tui_runner.py
from mcm_agent.tui.runner import run_with_spinner


def test_run_with_spinner_returns_result() -> None:
    assert run_with_spinner(lambda: 6 * 7, "Computing") == 42


def test_run_with_spinner_propagates_exception() -> None:
    import pytest

    with pytest.raises(ValueError):
        run_with_spinner(lambda: (_ for _ in ()).throw(ValueError("boom")), "X")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_runner.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# src/mcm_agent/tui/runner.py
from __future__ import annotations

import threading
from typing import Callable, TypeVar

from rich.console import Console

from mcm_agent.tui.theme import ACCENT

T = TypeVar("T")


def run_with_spinner(fn: Callable[[], T], verb: str, *, console: Console | None = None) -> T:
    """Run a blocking callable in a worker thread while showing a one-line spinner
    ('∑ <verb>… (esc 中断)'). Returns fn()'s result; re-raises its exception."""
    console = console or Console()
    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - propagate to caller
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    # Use the hex accent inline (not the theme name) so it renders even with a
    # plain Console that has no MAG_THEME registered.
    with console.status(f"[{ACCENT}]∑[/] {verb}… (esc 中断)", spinner="dots"):
        thread.start()
        thread.join()
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["result"]  # type: ignore[return-value]
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_runner.py -q`
Expected: PASS

- [ ] **Step 5: 接入 chat（spinner + markdown 渲染）** — 在 `_handle_natural_language` 把 `generate_chat_reply(...)` 包进 spinner：

```python
        from mcm_agent.tui.runner import run_with_spinner

        attachments = self._collect_attachments(text)
        reply = run_with_spinner(
            lambda: generate_chat_reply(
                self.workspace_root, text, self._chat_llm(), recent, attachments=attachments
            ),
            "正在思考",
            console=self.console,
        )
```

新增「chat 回复用 markdown 渲染」的辅助（区别于命令正文）：在 `_handle_natural_language` 返回前，将 reply 作为 markdown 打印而不是纯文本——把返回值改成由调用方渲染较复杂，改为本方法直接渲染并返回空消息会破坏 run_once 既有契约。**改用更小的改动**：保持返回 `CommandResult(reply)`，并在 `_run_plain`/`PromptUI` 渲染前，对「自然语言回复」用 markdown。最简实现：在 `CommandResult` 增加可选 `markdown: bool=False`，自然语言结果置 `True`，`_print` 分支渲染。

具体：`cli_commands/base.py` 的 `CommandResult` 增字段（向后兼容默认 False）：

```python
    markdown: bool = False
```

`_handle_natural_language` 的成功分支返回 `CommandResult(reply, markdown=True)`。

`InteractiveSession` 增渲染分支，并在两处渲染点（`_run_plain` 与 `PromptUI.loop`）调用它替代 `self._print(result.message)`：

```python
    def _render_result(self, result) -> None:
        if getattr(result, "markdown", False):
            from rich.markdown import Markdown

            self.console.print(Markdown(result.message))
        else:
            self._print(result.message)
```

> 注意：`markdown=True` 只用于自然语言回复；命令正文仍走 `_print(markup=False)`，保字面标记不变。

- [ ] **Step 6: 调整两处渲染点** — 把 `_run_plain` 与 `app.py` 中的 `self.session._print(result.message)` / `self._print(result.message)` 改为 `self._render_result(result)` / `self.session._render_result(result)`。

- [ ] **Step 7: 回归 + 提交**

```bash
python -m pytest -q
git add src/mcm_agent/tui/runner.py src/mcm_agent/cli_session.py src/mcm_agent/cli_commands/base.py src/mcm_agent/tui/app.py tests/test_tui_runner.py
git commit -m "feat(tui): spinner for LLM calls + markdown-rendered chat replies"
git push origin main
```

> **Phase 3 完成：推送 main。**

---

# Phase 4 — LLM 流式渲染（可选增强）

> 仅在 Phase 1-3 稳定后实施；非阻塞需求。先确认 provider 支持 SSE 流。

### Task 14: provider 流式 `generate_stream` + 流式渲染

**Files:**
- Modify: `src/mcm_agent/providers/llm.py`（`OpenAICompatibleLLMProvider.generate_stream`）
- Modify: `src/mcm_agent/core/chat.py`（`stream_chat_reply` 生成器，可选）
- Modify: `src/mcm_agent/cli_session.py`（自然语言走流式渲染）
- Test: `tests/test_llm_stream.py`（用假 SSE 响应）

**Interfaces:**
- Produces: `OpenAICompatibleLLMProvider.generate_stream(system, prompt) -> Iterator[str]`（逐块产出文本）

- [ ] **Step 1: 写失败测试**（用 monkeypatch 假 `httpx` 流，断言拼接结果）

```python
# tests/test_llm_stream.py
def test_generate_stream_yields_text_chunks(monkeypatch) -> None:
    from mcm_agent.providers.llm import OpenAICompatibleLLMProvider

    chunks = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
        'data: {"choices":[{"delta":{"content":" world"}}]}\n',
        "data: [DONE]\n",
    ]

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_lines(self): return iter(chunks)

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def stream(self, *a, **k): return _Resp()

    monkeypatch.setattr("mcm_agent.providers.llm.httpx.Client", _Client)
    provider = OpenAICompatibleLLMProvider(api_key="k", model="m", base_url="http://x/v1")

    assert "".join(provider.generate_stream("sys", "hi")) == "Hello world"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_llm_stream.py -q`
Expected: FAIL（`generate_stream` 不存在）

- [ ] **Step 3: 实现 `generate_stream`**（按现有 `OpenAICompatibleLLMProvider.generate` 的 base_url/headers 复用，改用 `client.stream("POST", url, json={... ,"stream": True})`，逐行解析 `data:` SSE，遇 `[DONE]` 结束，产出 `delta.content`）。具体代码以现有 `generate` 实现为蓝本，仅把请求体加 `"stream": True` 并迭代解析。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_llm_stream.py -q`
Expected: PASS

- [ ] **Step 5: 接入流式渲染**（在 `PromptUI` 路径用 `prompt_async` + `to_thread` + `patch_stdout`，对自然语言增量打印；非流式 provider/非 TTY 退回 Task 13 的 spinner 一次性渲染）。

- [ ] **Step 6: 回归 + 提交 + 推送**

```bash
python -m pytest -q
git add -A src/mcm_agent/providers/llm.py src/mcm_agent/core/chat.py src/mcm_agent/cli_session.py tests/test_llm_stream.py
git commit -m "feat(tui): optional LLM token streaming"
git push origin main
```

---

## 自审清单（写计划后自检）

- **Spec 覆盖**：欢迎面板(T5) / `/`补全(T7) / `@`文件(T11,T12) / `!`shell(T1,T2) / 状态行(T8) / 历史+多行(T9,T10) / spinner可中断(T13) / 主题(T4) / markdown 回复(T13) / 非TTY降级(T10) / 测试(各任务+T10冒烟) / 流式(T14) — 均有任务。
- **降级**：T10 的 `run()` 分流确保非 TTY 与 ImportError 都回退 `_run_plain`；既有 497 测试走 `run_once`，不受影响。
- **类型一致**：`ShellResult`(T1)↔`_run_shell`(T2)；`SlashCommandCompleter`(T7)↔`MagCompleter`(T11)↔`app.py`(T10/T11)；`generate_chat_reply(attachments=)`(T12)↔`_collect_attachments`(T12)↔spinner 包裹(T13)；`render_result.markdown` 字段(T13) 与 `CommandResult`(base.py) 一致。
- **占位符**：无 TBD/TODO；每代码步骤含真实代码与命令。
- **颜色/品牌**：全程 teal `#1D9E75` + `∑`，无珊瑚橙/✻。

## 阶段同步策略
- 每个 Task 一次提交；**每个 Phase 末尾 `git push origin main`**（P1 在 T5 后、P2 在 T10 后、P3 在 T13 后、P4 在 T14 后）。
- 仅提交 `src/`、`tests/`、`pyproject.toml`、`docs/`；**绝不** `git add -A` 把 `assets/`（版权题目）带入（T14 的 `git add -A` 已限定具体文件）。
