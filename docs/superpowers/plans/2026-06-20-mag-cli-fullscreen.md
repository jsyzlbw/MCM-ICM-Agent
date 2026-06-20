# Mag CLI — 全屏边框输入框应用（Bug 1 + 5 + 2）

> 把 TTY 交互从 `PromptSession` 行式 REPL 升级为 **prompt_toolkit 全屏 Application**，像 Claude Code：上方可滚动对话区（渲染我们的 rich 输出）+ 底部 `Frame` 边框输入框 + 模式感知上色 + 限宽。**机制已用原型验证可行**。Global Constraints 同前（teal `#1D9E75` + ∑、run_once 单入口、非 TTY 降级、markup 仅外壳、TDD、只提交具体文件）。

已验证的关键机制（原型 `/tmp/pt_proto.py` 跑通）：full_screen `Application` + `FloatContainer`(`CompletionsMenu` float) + `HSplit([transcript Window, Frame(input TextArea)])`；transcript 用 `FormattedTextControl(get_transcript)` 显示 `merge_formatted_text([ANSI(...)])`；append 后 `window.vertical_scroll = 10**9` 由 pt 钳到底部；pipe input 可驱动（可测）。

---

## Task FS-1: 全屏应用 `tui/fullscreen.py`

**Files:**
- Create: `src/mcm_agent/tui/fullscreen.py`
- Modify: `src/mcm_agent/cli_session.py`（`run()` TTY 分流改为优先全屏 App）
- Test: `tests/test_tui_fullscreen.py`

**Interfaces:**
- Consumes: `InteractiveSession`（`run_once`、`_run_shell`、`workspace_root`、`commands`、`session_store`、`_collect_attachments`）；`MagCompleter`（completers）；`bottom_toolbar`（statusbar）；`ACCENT`/`MAG_THEME`（theme）；`render_welcome_panel`（welcome）；`Interrupted`/`run_with_spinner` 思路（runner，可选）。
- Produces: `class MagFullScreenApp` with `__init__(self, session, *, input=None, output=None)` 和 `run(self)`；模块级 `def render_to_ansi(renderable, width) -> ANSI`。

### 设计

布局（上→下）：
1. `transcript`：`Window(FormattedTextControl(get_transcript, focusable=False), wrap_lines=True)`。`get_transcript` 返回 `merge_formatted_text(self._fragments)`（`self._fragments: list[ANSI]`）。
2. `Frame(input_area, title=<dynamic mode title>)`：`input_area = TextArea(height=Dimension(min=1, max=8), multiline=True, completer=MagCompleter(...), focus_on_click=True, prompt="> ")`。
3. `Window(FormattedTextControl(lambda: ANSI-of-statusbar), height=1)`：底部状态行。

外层 `FloatContainer(content=HSplit([...]), floats=[Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=8, scroll_offset=1))])`。

**模式感知（Bug 5）**：根据 `input_area.text` 的首字符算模式：`!`→("shell", ACCENT 暖色如 `#EF9F27`)、`/`→("命令", ACCENT)、`@`→("文件", `#5DCAA5`)、else→("讨论", ACCENT)。`Frame` 的 `title` 传一个**可调用**返回 `f" {badge} "`；边框色用动态 `style`（`Frame` 不直接支持动态 border 色，则把 mode badge 放 title + 在 input 的 `prompt`/文本上色即可；至少 title 随模式变）。`bottom_toolbar` 文案也追加当前模式。

**提交处理**（Enter）：
- 取 `text = input_area.text`；空则忽略。
- `input_area.buffer.reset()` 清空。
- 把用户输入回显进 transcript：`self._append(render_to_ansi(Text("> "+text, style=ACCENT)))`。
- 路由：`text.startswith("!")` → 后台线程跑 `session._run_shell(text[1:].strip())`；否则后台线程跑 `session.run_once(text)`。
- **后台执行**（避免冻结 UI）：用 `asyncio` 把阻塞调用丢线程：`result = await loop.run_in_executor(None, session.run_once, text)`；其间 transcript 末尾显示一行 `∑ 正在处理…`（处理完移除/替换）。Enter 处理器是 async（pt 支持 `async def` key handler）。
- 渲染结果：`CommandResult.message` —— 若 `getattr(result,"markdown",False)` 用 `render_to_ansi(Markdown(msg), width)`，否则 `render_to_ansi(Text(msg), width)`（保持 markup=False 字面）。append 后 `_pin_bottom()` + `app.invalidate()`。
- `result.exit_session` → `app.exit()`。

**限宽（Bug 2）**：`render_to_ansi(renderable, width)` 用 `Console(width=width, force_terminal=True, color_system="standard")` capture；`width = min(app 可用列 or os.get_terminal_size().columns) - 2, 100)`（上限 100，避免超宽铺满）。

**欢迎面板**：`run()` 开始时 `self._append(render_to_ansi(render_welcome_panel(state, settings, __version__, root), width))`。

**键位**：复用思路——Enter 提交（async handler）；`escape,enter`(Alt+Enter) 插入换行；`c-c` 两次退出（第一次清空当前输入并提示）；`c-d` 退出；`?` 单独 → 走 run_once("?")（已支持）。Esc：若有后台任务在跑则尝试中断（设标志；至少停止"正在处理"显示）；否则关闭补全菜单（pt 默认）。

**焦点/光标**：transcript `focusable=False`，焦点恒在 `input_area`。

### TDD 步骤

- [ ] **Step 1: 失败测试**（pipe input 驱动，无需真 TTY；断言提交 → transcript 收到输出 + run_once 被调用）

```python
# tests/test_tui_fullscreen.py
from pathlib import Path

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace
from mcm_agent.tui.fullscreen import MagFullScreenApp, render_to_ansi


def test_render_to_ansi_caps_width() -> None:
    from rich.text import Text

    out = render_to_ansi(Text("hello"), width=40)
    # ANSI object exposes its text via .value
    assert "hello" in out.value


def test_fullscreen_submits_to_run_once(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)
    seen: list[str] = []
    orig = session.run_once
    session.run_once = lambda text: seen.append(text) or orig(text)  # type: ignore

    with create_pipe_input() as inp:
        inp.send_text("?\r")        # a command that run_once handles (shortcuts help)
        inp.send_text("\x04")       # Ctrl-D exits
        MagFullScreenApp(session, input=inp, output=DummyOutput()).run()

    assert "?" in seen  # input was dispatched through run_once


def test_fullscreen_bang_runs_shell(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    with create_pipe_input() as inp:
        inp.send_text("!echo fs-ok\r")
        inp.send_text("\x04")
        app = MagFullScreenApp(session, input=inp, output=DummyOutput())
        app.run()

    # the shell output was appended to the transcript
    joined = "".join(frag.value for frag in app._fragments)
    assert "fs-ok" in joined
```

- [ ] **Step 2: 运行确认失败** — `python -m pytest tests/test_tui_fullscreen.py -q` → ModuleNotFound。

- [ ] **Step 3: 实现 fullscreen.py**（按上面设计；参考原型 `/tmp/pt_proto.py` 已验证的构造方式：FloatContainer + CompletionsMenu float + Frame(TextArea) + FormattedTextControl(merge_formatted_text) + vertical_scroll=10**9 钳底）。注意：Enter 用 async key handler 经 `loop.run_in_executor` 跑 `run_once`，避免与 `accept_handler` 重复触发（只用其一）。`render_to_ansi` 用 capture。

- [ ] **Step 4: 运行确认通过** — `python -m pytest tests/test_tui_fullscreen.py -q`。

- [ ] **Step 5: 接入 `run()` 分流** — 改 `cli_session.run()`：

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
            from mcm_agent.tui.fullscreen import MagFullScreenApp
        except ImportError:
            return self._run_plain()
        try:
            MagFullScreenApp(self).run()
        except Exception:
            # any TUI failure must not strand the user — fall back to the plain loop
            self._run_plain()
```

（保留 `_run_plain`/`_print_welcome`；`PromptUI`（旧行式 pt）可留作未使用或删除——本任务保留以免动测试，不再被 `run()` 调用。）

- [ ] **Step 6: 全量回归** — `python -m pytest -q`（应仍 541+ 全绿：非 TTY 走 `_run_plain`，全屏 App 仅 TTY；新 fullscreen 测试用 pipe input）。

- [ ] **Step 7: 真机手测 + 提交** — 真终端 `mag`：应见**底部边框输入框** + 上方滚动对话区；输入 `!` 时 Frame 标题/样式变"shell"；`/` 弹补全；长回复 markdown 渲染且不超宽。

```bash
git add src/mcm_agent/tui/fullscreen.py src/mcm_agent/cli_session.py tests/test_tui_fullscreen.py
git commit -m "feat(tui): full-screen bordered-input app (scrolling transcript + mode-aware input)"
```

> 完成后推送 main。

### 风险
- 全屏 App 在某些终端的渲染差异：保留非 TTY/异常 → `_run_plain` 兜底。
- `loop.run_in_executor` 跑 `run_once`：`run_once` 内部有 `session_store` 写文件，线程安全（仅追加），可接受。
- vertical_scroll 钳底在极少数 pt 版本行为差异：原型在 3.0.52 验证 OK（已 pin）。
- Esc 真中断后台 in-flight LLM 仍受限（同既有 spinner 局限）——至少 UI 不冻结。
