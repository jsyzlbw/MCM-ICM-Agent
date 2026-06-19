# Phase 3: 对话式 CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `mag` 真正"对话式"：用户能在 CLI 里用自然语言与 Agent 讨论题目；讨论阶段询问并锁定论文语言并贯通到写作；workflow 运行时显示人类可读进度。

**Architecture:** 复用 Phase 1 的配置/Provider 接线（`load_settings(workspace_root)` + `build_provider_bundle`）。自然语言路径接真实 LLM（带 workspace 上下文：题面 + 近期对话 + 状态）；论文语言经 `/start --language` 或交互询问写入 state + research script + `direction_lock.json`，并注入 writer 的 system prompt（中文→中文写作）；workflow 执行时把 stage 翻译成人类可读进度行。

**Tech Stack:** 现有 `mcm_agent` cli_session/cli_commands/agents/providers、pytest、ruff。

**对应 spec:** `docs/superpowers/specs/2026-06-19-mag-real-paper-engine-design.md`（§7 + 缺陷 B）。

---

## 背景事实（已核查）

- `cli_session._handle_natural_language`：无草稿时回固定话术，未接 LLM。
- `cli_commands/start.py`：用确定性 `build_initial_research_script`，不询问语言。
- `agents/discussion.py`：`UserDiscussionAgent.confirm_direction(..., language=...)` 已写 `direction_lock.json.language`；`confirmed_language(workspace_root)` 可读取。
- `agents/writer.py::_generate_results_section`：system prompt 写死英文，不读 `confirmed_language`。
- Provider 接线：`WorkspaceWorkflowAdapter.build_providers()`（Phase 1）可复用获取真实 LLM；`provider=fake` 时为离线。
- LaTeX 导言区已 CJK 感知（Phase 1）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `src/mcm_agent/cli_session.py` | NL 路径接 LLM（带上下文）；运行进度回调 | 修改 |
| `src/mcm_agent/core/chat.py` | NL 对话 helper（构造上下文 + 调 LLM + 回退） | 新建 |
| `src/mcm_agent/cli_commands/start.py` | `--language` 选项；写入 state/research script | 修改 |
| `src/mcm_agent/core/research_script.py` | research script 带 language 字段 | 修改 |
| `src/mcm_agent/agents/writer.py` | results section system prompt 随语言切换 | 修改 |
| `tests/test_chat.py` | NL 对话接 LLM + 回退 | 新建 |
| `tests/test_start_language.py` | `/start --language` 持久化 | 新建 |
| `tests/test_cli_interactive.py` | NL 行为更新 | 修改 |

每个 Task：`pytest -q` + `ruff` 绿 → commit → push main。

---

## Task 1: 自然语言对话接真实 LLM

**Files:**
- Create: `src/mcm_agent/core/chat.py`
- Modify: `src/mcm_agent/cli_session.py`
- Test: `tests/test_chat.py`

设计：`generate_chat_reply(workspace_root, message, llm_provider, recent_messages) -> str`。构造上下文（题面前 N 字 + 近期对话 + 状态摘要），调 `llm_provider.generate(system, prompt).content`；`llm_provider is None` → 返回引导性回退文案。`cli_session._handle_natural_language` 无草稿分支改为：构建 provider（`WorkspaceWorkflowAdapter(root).build_providers()` 的 llm），调 `generate_chat_reply`。

- [ ] **Step 1: 写失败测试** `tests/test_chat.py`

```python
from pathlib import Path

from mcm_agent.core.chat import generate_chat_reply
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.base import ProviderResult


class _EchoLLM:
    def __init__(self):
        self.last_prompt = ""

    def generate(self, system: str, prompt: str) -> ProviderResult:
        self.last_prompt = prompt
        return ProviderResult(content="讨论回复：建议先估计 fan votes。", metadata={})


def test_chat_reply_uses_llm_and_problem_context(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    (root / "input" / "problem").mkdir(parents=True, exist_ok=True)
    (root / "input" / "problem" / "p.md").write_text("Estimate hidden fan votes for DWTS.", encoding="utf-8")
    llm = _EchoLLM()

    reply = generate_chat_reply(root, "第一问怎么做？", llm, [])

    assert "fan votes" in reply or "讨论回复" in reply
    assert "DWTS" in llm.last_prompt  # problem context injected


def test_chat_reply_without_llm_returns_guidance(tmp_path: Path) -> None:
    root = create_workspace(tmp_path / "ws").root
    reply = generate_chat_reply(root, "你好", None, [])
    assert "/start" in reply
```

- [ ] **Step 2: 运行确认失败** `pytest tests/test_chat.py -q` → FAIL（模块不存在）。

- [ ] **Step 3: 实现 `core/chat.py`**

```python
from __future__ import annotations

from pathlib import Path

from mcm_agent.utils.json_io import read_json


def _problem_excerpt(workspace_root: Path, limit: int = 1500) -> str:
    problem_dir = workspace_root / "input" / "problem"
    if problem_dir.exists():
        files = sorted(p for p in problem_dir.iterdir() if p.is_file())
        if files:
            try:
                return files[0].read_text(encoding="utf-8")[:limit]
            except UnicodeDecodeError:
                return ""
    return ""


def generate_chat_reply(workspace_root, message, llm_provider, recent_messages):
    if llm_provider is None:
        return (
            "我已记录你的想法。要正式分析题目、与我深入讨论研究方向，请运行 /start；"
            "需要配置 LLM 请运行 /api。"
        )
    problem = _problem_excerpt(Path(workspace_root))
    history = "\n".join(
        f"{m.get('role')}: {m.get('content')}" for m in (recent_messages or [])[-6:]
        if isinstance(m, dict)
    )
    system = (
        "You are Mag, a math-modeling (MCM/ICM) research assistant. Discuss the problem, "
        "clarify the research direction, and give concrete, actionable modeling advice. "
        "Reply in the user's language."
    )
    prompt = "\n\n".join(
        part for part in [
            f"PROBLEM:\n{problem}" if problem else "",
            f"RECENT DISCUSSION:\n{history}" if history else "",
            f"USER:\n{message}",
        ] if part
    )
    return llm_provider.generate(system, prompt).content.strip()
```

- [ ] **Step 4: 接入 `cli_session._handle_natural_language`**（无草稿分支）：

```python
        # ... after guard passes, before draft check stays the same ...
        if self._has_draft():
            # existing revision-plan path unchanged
            ...
        from mcm_agent.core.chat import generate_chat_reply
        from mcm_agent.core.workflow_adapter import WorkspaceWorkflowAdapter
        try:
            _settings, bundle = WorkspaceWorkflowAdapter(self.workspace_root).build_providers()
            llm = bundle.llm
        except Exception:
            llm = None
        recent = self.session_store.read_recent_messages(limit=8) if hasattr(self.session_store, "read_recent_messages") else []
        reply = generate_chat_reply(self.workspace_root, text, llm, recent)
        return CommandResult(reply)
```

> 注：`FakeLLMProvider` 返回空 content；为避免空回复，`generate_chat_reply` 在 content 为空时回退到引导文案（在实现里加：`reply = ...content.strip(); return reply or <guidance>`）。

- [ ] **Step 5: 运行确认通过 + 回归** `pytest tests/test_chat.py tests/test_cli_interactive.py tests/test_dialogue_guard.py -q`。更新 `test_cli_interactive.py` 中对旧固定话术的断言（如有）。

- [ ] **Step 6: 提交** `git commit -m "feat: natural-language CLI chat wired to the LLM with problem context"`。

---

## Task 2: 讨论锁定论文语言并贯通写作

**Files:**
- Modify: `src/mcm_agent/cli_commands/start.py`、`src/mcm_agent/core/research_script.py`、`src/mcm_agent/agents/writer.py`
- Test: `tests/test_start_language.py`

- [ ] **Step 1: 写失败测试** `tests/test_start_language.py`：`/start --language zh --lock` 后 `direction_lock.json`/research script 含 `language=="zh"`；`confirmed_language(root)=="zh"`。

- [ ] **Step 2: 运行确认失败**。

- [ ] **Step 3: 实现**：`start.py` 解析 `--language`（默认 en），写入 research script + `discussion/direction_lock.json`（复用 `DiscussionDecision` 或直接写 language 键）+ `state`。`research_script.py` 增 `language` 字段。`writer.py::_generate_results_section` 读取 `confirmed_language(workspace_root)`，中文时 system prompt 改为中文写作指令（"用中文撰写，可保留英文缩写"）。

- [ ] **Step 4: 运行确认通过 + 回归** `pytest tests/test_start_language.py tests/test_research_script.py tests/test_llm_agents.py -q`。

- [ ] **Step 5: 提交** `git commit -m "feat: ask+thread paper language from discussion into writing"`。

---

## Task 3: 运行时人类可读进度

**Files:**
- Modify: `src/mcm_agent/cli_commands/start.py`、`src/mcm_agent/core/workflow_adapter.py`
- Test: `tests/test_status_outputs.py`（或新建）

- [ ] **Step 1**: `workflow_adapter.run_default_workflow(progress=callable|None)`：用现有 `run_mvp_workflow(..., controller=...)` 或 stage 事件，把 stage_id 映射为人类可读文案（正在理解题目/检查数据/写代码求解/画图/写论文/审查/打包），通过 `progress(text)` 回调输出。
- [ ] **Step 2**: `start.py` 传入打印到 console 的 progress 回调。
- [ ] **Step 3**: 测试：注入 progress 收集器，断言关键阶段文案出现。
- [ ] **Step 4**: 提交 `git commit -m "feat: human-readable workflow progress in CLI"`。

---

## Task 4: Phase 3 真题回归

- [ ] **Step 1**: `pytest -q && ruff check src tests scripts` 全绿。
- [ ] **Step 2**: 交互式 smoke（session harness）：`/question`→`/data`→`/init --llm-key ... --llm-base-url ... --llm-model ...`→自然语言讨论一轮（真实 LLM 回复）→`/start --language en --lock --run`→产出 PDF。
- [ ] **Step 3**: 人工确认对话有真实回复、进度可读、PDF 语言正确。
- [ ] **Step 4**: 更新 `docs/` 实现状态 + 提交。

---

## Self-Review 检查

- **Spec 覆盖**：讨论接 LLM（T1）、语言询问+贯通（T2）、进度（T3）、验收（T4）。
- **类型一致**：`generate_chat_reply(workspace_root, message, llm_provider, recent_messages) -> str`；`build_providers()`（Phase 1 已加）。
- **回退**：无 LLM/fake 时 NL 给引导文案，不报错。
- **风险**：session 读历史方法名需核对（`SessionStore`）；不破坏现有交互测试（更新旧断言）。
