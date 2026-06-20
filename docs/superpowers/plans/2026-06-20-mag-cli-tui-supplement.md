# Mag CLI TUI — 补充计划 (Phase 3.5 + Phase 4)

> 续 docs/superpowers/plans/2026-06-20-mag-cli-tui.md。关闭终审发现的 3 个 spec 缺口（Phase 3.5）+ 实现 Phase 4 流式。Global Constraints 同主计划（teal #1D9E75 + ∑、run_once 单入口、markup=False 仅外壳上色、非 TTY 降级、TDD、仅提交具体文件不用 git add -A）。

---

## Task 15: run_with_spinner 真支持 Esc / Ctrl+C 中断

**Files:**
- Modify: `src/mcm_agent/tui/runner.py`（加 Interrupted + 取消轮询）
- Modify: `src/mcm_agent/cli_session.py`（`_handle_natural_language` 捕获 Interrupted）
- Test: `tests/test_tui_runner.py`（追加）

**Interfaces:**
- Produces: `class Interrupted(Exception)`；`run_with_spinner(fn, verb, *, console=None, cancel_check=None) -> T`（新增 cancel_check 形参；Esc(TTY) 或 Ctrl+C → 抛 Interrupted）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_tui_runner.py
def test_run_with_spinner_cancel_raises_interrupted() -> None:
    import time

    import pytest

    from mcm_agent.tui.runner import Interrupted, run_with_spinner

    with pytest.raises(Interrupted):
        run_with_spinner(lambda: time.sleep(1) or 1, "X", cancel_check=lambda: True)
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_runner.py::test_run_with_spinner_cancel_raises_interrupted -q`
Expected: FAIL（ImportError: Interrupted / cancel_check 未支持）

- [ ] **Step 3: 重写 runner.py**

```python
# src/mcm_agent/tui/runner.py
from __future__ import annotations

import contextlib
import select
import sys
import threading
from typing import Callable, TypeVar

from rich.console import Console

from mcm_agent.tui.theme import ACCENT

T = TypeVar("T")


class Interrupted(Exception):
    """User abandoned a long operation (Esc on a TTY, or Ctrl+C) while the spinner
    was active. The worker thread is a daemon; its result is discarded."""


def _stdin_esc_waiting() -> bool:
    """True if a lone ESC byte is pending on a TTY stdin. False on non-TTY / error."""
    try:
        if not sys.stdin.isatty():
            return False
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return False
        return sys.stdin.read(1) == "\x1b"
    except Exception:
        return False


def _cbreak_stdin():
    """Context manager putting the TTY into cbreak so a single Esc is readable
    without Enter. No-op when termios is unavailable or stdin is not a TTY."""
    try:
        import termios
        import tty
    except ImportError:
        return contextlib.nullcontext()
    if not sys.stdin.isatty():
        return contextlib.nullcontext()

    @contextlib.contextmanager
    def _ctx():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return _ctx()


def run_with_spinner(
    fn: Callable[[], T],
    verb: str,
    *,
    console: Console | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> T:
    """Run fn() in a worker thread with a live spinner. Returns fn()'s result;
    re-raises fn's exception. Raises Interrupted if the user presses Esc (TTY) or
    Ctrl+C while waiting."""
    console = console or Console()
    cancel_check = cancel_check or _stdin_esc_waiting
    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - propagate to caller
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    try:
        with console.status(f"[{ACCENT}]∑[/] {verb}… (esc 中断)", spinner="dots"):
            with _cbreak_stdin():
                thread.start()
                while thread.is_alive():
                    if cancel_check():
                        raise Interrupted()
                    thread.join(timeout=0.1)
    except KeyboardInterrupt:
        raise Interrupted() from None
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["result"]  # type: ignore[return-value]
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_runner.py -q`
Expected: PASS（3 passed：含既有 returns/propagates + 新 cancel）

- [ ] **Step 5: chat 捕获 Interrupted** — 在 `cli_session.py` 的 `_handle_natural_language` 中，把对 `run_with_spinner(...)` 的调用用 try 包住：

```python
        from mcm_agent.tui.runner import Interrupted, run_with_spinner

        attachments = self._collect_attachments(text)
        try:
            reply = run_with_spinner(
                lambda: generate_chat_reply(
                    self.workspace_root, text, self._chat_llm(), recent, attachments=attachments
                ),
                "正在思考",
                console=self.console,
            )
        except Interrupted:
            return CommandResult("（已中断当前回复。）")
        return CommandResult(reply, markdown=True)
```

（即：保留 Task 13 的 spinner 包裹，仅加 try/except Interrupted 与导入 Interrupted。读当前 `_handle_natural_language` 精确替换那几行。）

- [ ] **Step 6: 回归 + 提交**

```bash
python -m pytest -q
git add src/mcm_agent/tui/runner.py src/mcm_agent/cli_session.py tests/test_tui_runner.py
git commit -m "feat(tui): real Esc/Ctrl+C interrupt for the spinner (Interrupted)"
```

---

## Task 16: 裸 `?` 显示快捷键帮助

**Files:**
- Modify: `src/mcm_agent/cli_session.py`（`run_once` 加 `?` 分支 + `_shortcuts_help`）
- Test: `tests/test_shortcuts_help.py`

**Interfaces:**
- Produces: 输入恰为 `?` 时，`run_once` 返回快捷键/模式帮助文本

- [ ] **Step 1: 写失败测试**

```python
# tests/test_shortcuts_help.py
from pathlib import Path

from mcm_agent.cli_session import InteractiveSession
from mcm_agent.core.workspace import create_workspace


def test_question_mark_shows_shortcuts(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    session = InteractiveSession(root)

    result = session.run_once("?")

    assert "快捷键" in result.message
    assert "Ctrl+C" in result.message
    assert "!" in result.message and "@" in result.message
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_shortcuts_help.py -q`
Expected: FAIL（`?` 当前走自然语言）

- [ ] **Step 3: 实现** — 在 `run_once` 中，紧接 `self.session_store.append_message("user", stripped)` 之后、`if stripped.startswith("!"):` 之前插入：

```python
        if stripped == "?":
            return CommandResult(self._shortcuts_help())
```

新增方法：

```python
    def _shortcuts_help(self) -> str:
        return "\n".join(
            [
                "快捷键 / 输入模式：",
                "  /          命令补全菜单（/start /api /question …）",
                "  !          执行 shell 命令，例如 !ls input/data",
                "  @          引用工作区文件（题目 / 数据 / 产出）",
                "  ↑ / ↓      历史输入",
                "  Alt+Enter  多行输入（Enter 提交）",
                "  Esc        中断进行中的任务",
                "  Ctrl+C ×2  退出",
                "  /help      查看全部命令",
            ]
        )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_shortcuts_help.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/cli_session.py tests/test_shortcuts_help.py
git commit -m "feat(tui): bare ? shows shortcuts help"
```

---

## Task 17: /start --run 期间逐阶段 live spinner

**Files:**
- Modify: `src/mcm_agent/tui/runner.py`（加 `format_stage` 纯函数）
- Modify: `src/mcm_agent/cli_commands/start.py`（--run 分支用 live spinner 包裹工作流，progress 更新 status）
- Test: `tests/test_tui_runner.py`（追加 format_stage 单测）

**Interfaces:**
- Produces: `format_stage(text: str) -> str`（返回 `∑ {text}` 形态、带 accent 标记的状态行文本，供 spinner 更新）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_tui_runner.py
def test_format_stage_prefixes_accent_sigma() -> None:
    from mcm_agent.tui.runner import format_stage

    out = format_stage("正在写代码求解")
    assert "正在写代码求解" in out
    assert "∑" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_tui_runner.py::test_format_stage_prefixes_accent_sigma -q`
Expected: FAIL（format_stage 未定义）

- [ ] **Step 3: 实现 format_stage**（追加到 runner.py）

```python
def format_stage(text: str) -> str:
    """Status-line text for a workflow stage, with the ∑ brand in accent color."""
    return f"[{ACCENT}]∑[/] {text}"
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_tui_runner.py -q`
Expected: PASS

- [ ] **Step 5: 接入 start.py** — 读 `start.py` 的 `--run` 分支（当前用 `progress = (lambda text: printer(f"… {text}"))` 然后 `WorkspaceWorkflowAdapter(root).run_default_workflow(auto_approve=True, progress=progress)`）。替换为 live spinner：

```python
            if "--run" in args:
                from rich.console import Console as _Console

                from mcm_agent.tui.runner import format_stage
                from mcm_agent.tui.theme import MAG_THEME

                console = _Console(theme=MAG_THEME)
                with console.status(format_stage("正在求解…"), spinner="dots") as status:
                    WorkspaceWorkflowAdapter(root).run_default_workflow(
                        auto_approve=True,
                        progress=lambda text: status.update(format_stage(text)),
                    )
                return CommandResult(
                    "Research script locked and workflow completed. See output/draft and output/package."
                )
```

（`console.status` 在非 TTY 下自动降级为无动画，不影响 `--run` 的既有测试。）

- [ ] **Step 6: 回归 + 提交**

```bash
python -m pytest -q
git add src/mcm_agent/tui/runner.py src/mcm_agent/cli_commands/start.py tests/test_tui_runner.py
git commit -m "feat(tui): live per-stage spinner during /start --run"
```

> **Phase 3.5 完成：推送 main。** `git push origin main`

---

## Task 14: LLM 流式（Phase 4）

**Files:**
- Modify: `src/mcm_agent/providers/llm.py`（`OpenAICompatibleLLMProvider.generate_stream`）
- Modify: `src/mcm_agent/core/chat.py`（`stream_chat_reply` 生成器）
- Modify: `src/mcm_agent/cli_session.py`（自然语言：能流式则逐块打印，否则回退 spinner）
- Test: `tests/test_llm_stream.py`、`tests/test_chat_stream.py`

**Interfaces:**
- Produces: `OpenAICompatibleLLMProvider.generate_stream(system, prompt) -> Iterator[str]`；`chat.stream_chat_reply(workspace_root, message, llm_provider, recent_messages, attachments=None) -> Iterator[str]`

- [ ] **Step 1: 写 provider 流式失败测试**

```python
# tests/test_llm_stream.py
def test_generate_stream_yields_text_chunks(monkeypatch) -> None:
    from mcm_agent.providers.llm import OpenAICompatibleLLMProvider

    chunks = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        "data: [DONE]",
    ]

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter(chunks)

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("mcm_agent.providers.llm.httpx.Client", _Client)
    provider = OpenAICompatibleLLMProvider(api_key="k", model="m", base_url="http://x/v1")

    assert "".join(provider.generate_stream("sys", "hi")) == "Hello world"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_llm_stream.py -q`
Expected: FAIL（generate_stream 未定义）

- [ ] **Step 3: 实现 generate_stream** — 先读 `src/mcm_agent/providers/llm.py` 的 `OpenAICompatibleLLMProvider.generate`，复用其 `base_url`/`headers`/`model`/`api_key` 构造与 URL（`{base_url}/chat/completions`）。新增方法，请求体加 `"stream": True`，用 `httpx.Client(timeout=...)` 的 `client.stream("POST", url, headers=..., json=...)`，逐行 `iter_lines()`：去掉 `data: ` 前缀；`[DONE]` 结束；`json.loads` 后取 `choices[0]["delta"].get("content")`，非空则 `yield`。解析异常的行跳过。示例骨架：

```python
    def generate_stream(self, system: str, prompt: str):
        import json

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[len("data: ") :]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        delta = json.loads(line)["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, ValueError):
                        continue
                    if delta:
                        yield delta
```

> 注意：用实现里实际的 headers 构造（读现有 `generate`，可能是 `self._headers()` 或内联 dict，含 `Authorization: Bearer`）。`self.base_url` 是否已含 `/v1` 取决于现有实现——与 `generate` 保持一致。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_llm_stream.py -q`
Expected: PASS

- [ ] **Step 5: chat.stream_chat_reply** — 写失败测试 `tests/test_chat_stream.py`（用一个有 `generate_stream` 的假 provider，断言把题目/附件/USER 拼进 prompt 且产出拼接等于各 chunk），再实现 `stream_chat_reply`：复用 `generate_chat_reply` 的 system/prompt 拼装（抽出共享的 `_build_prompt(workspace_root, message, recent_messages, attachments)` 以 DRY），然后 `yield from llm_provider.generate_stream(system, prompt)`。`_build_prompt` 同时被 `generate_chat_reply` 复用（重构，保持其现有测试绿）。

```python
# tests/test_chat_stream.py
from pathlib import Path

from mcm_agent.core.chat import stream_chat_reply
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


class _StreamLLM:
    def __init__(self):
        self.last_prompt = ""

    def generate(self, system, prompt):
        return ProviderResult(content="x", metadata={})

    def generate_stream(self, system, prompt):
        self.last_prompt = prompt
        for chunk in ["建议", "先估计", "票数"]:
            yield chunk


def test_stream_chat_reply_yields_chunks_and_injects_context(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text("DWTS fan votes.", encoding="utf-8")
    llm = _StreamLLM()

    out = "".join(stream_chat_reply(root, "第一问？", llm, [], attachments=[("d.csv", "a,b")]))

    assert out == "建议先估计票数"
    assert "DWTS" in llm.last_prompt
    assert "d.csv" in llm.last_prompt
```

- [ ] **Step 6: 接入自然语言流式** — 在 `_handle_natural_language` 中：当 `self._chat_llm()` 具有 `generate_stream`（`hasattr`）且 `self.console` 输出为 TTY 时，逐块打印（`self.console.print(chunk, end="")`）并累积全文，结束后追加换行；把全文存入 session_store，返回 `CommandResult("")`（已自行打印，避免重复渲染）。否则走 Task 13/15 的 spinner+markdown 路径。被 Interrupted 时停止打印并提示。流式分支不强求 markdown 渲染（逐块 raw 打印）。给该分支补一个面向 run_once 的测试：注入一个带 generate_stream 的假 llm 时仍不崩、store 收到 assistant 文本。

- [ ] **Step 7: 回归 + 提交 + 推送**

```bash
python -m pytest -q
git add src/mcm_agent/providers/llm.py src/mcm_agent/core/chat.py src/mcm_agent/cli_session.py tests/test_llm_stream.py tests/test_chat_stream.py
git commit -m "feat(tui): optional LLM token streaming for chat"
git push origin main
```

> **Phase 4 完成：推送 main。**
