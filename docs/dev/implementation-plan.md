# Mag Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按当前中文设计文档实现 Mag：一个安装后输入 `mag` 即可工作的本地命令行数学建模
Agent，具备 workspace、Git 安全网、API 配置、RAG、题目/数据导入、研究脚本锁定、自动建模写作、
审查修订和可选 GitHub 同步。

**Architecture:** 采用 CLI-first、workspace-centered 的架构。第一阶段不引入常驻 daemon，
而是在单进程 CLI 内建立清晰的 runtime boundary：CLI shell、slash command、workspace safety、
event log、agent workflow adapter、provider registry 分层独立。后续如果需要 TUI/Web/daemon，
可以沿着 KamaClaude 式的 event bus + typed protocol 演进，不推翻核心模块。

**Tech Stack:** Python 3.12+、Typer、Rich、Pydantic、python-dotenv、pytest、ruff、现有
`mcm_agent` workflow/agents/providers/solver 模块、本地 Git CLI、可选 GitHub CLI 或 GitHub API。

---

## 1. 外部项目参考与取舍

本计划参考以下开源 Agent 项目，但只吸收适合 Mag 当前阶段的设计。

| 项目 | 可借鉴点 | Mag 的取舍 |
|---|---|---|
| [KamaClaude](https://github.com/youngyangyang04/KamaClaude) | daemon + CLI/TUI 分离、JSON-RPC over NDJSON、EventBus、权限审批、trace、session/thread/notes、context compact、skills/subagents/MCP。 | 第一阶段不做 daemon，先实现 typed event log、session store、permission policy 和 command boundary；daemon/TUI 放到后续可选阶段。 |
| [OpenCode](https://opencode.ai/docs/) | 一键安装、终端 TUI、slash commands、provider connect、可扩展 tools/rules/agents/models/permissions。 | 保持裸 `mag` 交互体验；先实现 `/api`、`/init`、`/start` 等核心命令，rules/skills/MCP 后置。 |
| [Aider](https://aider.chat/docs/) | terminal-first、in-chat commands、chat modes、`.env` 配置、Git-first 工作流。 | 采用 Git checkpoint 作为默认安全网；Mag 的 chat mode 先固定为“建模讨论 + 执行”，以后再扩展 ask/plan/act。 |
| [Cline](https://cline.bot/) | Plan/Act、human-in-the-loop approval、checkpoints、one-click undo、MCP/hooks、多 agent teams。 | Mag 的 `/start` 前必须锁定 research script；高风险文件操作走 Git checkpoint 和权限策略；MCP/hooks 后置。 |
| [OpenHands](https://openreview.net/forum?id=OJd3ayDDoF) | agent + tools + workspace + sandbox 思路，支持写代码、命令行、浏览器和 benchmark。 | Mag 不做通用软件工程平台，但采用“工具执行必须有 workspace 边界、日志和测试”的思想。 |
| [OpenHands Software Agent SDK](https://github.com/OpenHands/software-agent-sdk) | Agent、Tool、Conversation、Workspace 的清晰 SDK 边界，可本地 workspace 或 ephemeral workspace。 | Mag 的 agent workflow adapter 也按 Conversation/Workspace/Tool boundary 设计，方便后续替换或外接 runtime。 |
| [Goose](https://github.com/aaif-goose/goose) | 本地 Agent，同步支持 Desktop、CLI、API，多 provider 与 MCP extension。 | Mag 先做 CLI 和内部 API 边界，桌面和 Web 视为可选客户端，不作为当前主路径。 |

核心判断：

1. Mag 是数学建模 Agent，不是通用 coding agent，所以 workflow、artifact contract、paper quality gate 比通用工具生态更重要。
2. 参考 KamaClaude 的运行时边界，但不在 P0 引入 daemon，避免过早增加 IPC、并发和进程管理复杂度。
3. 参考 Aider/Cline 的 Git 安全网，但 Mag 需要更严格地排除 `.env`、题目私有数据和敏感缓存。
4. 参考 OpenCode/Goose 的 provider 可扩展性，但 Mag 的 `/init` 只强制 LLM，其他 API 延迟配置。

## 2. 目标完成定义

实现完成时，用户应能完成以下端到端流程：

```text
curl -fsSL <install-url> | bash
mkdir 2026-mcm-c
cd 2026-mcm-c
mag
  -> 自动创建 workspace
  -> 自动创建 Git 仓库和初始 checkpoint
  -> 进入交互界面
  -> /init 配置 LLM，选择可选 API，导入题目/数据/RAG/模板
  -> /start 分析题目，与用户讨论研究方向
  -> 检查数据可得性
  -> 锁定 research script
  -> 运行现有 workflow
  -> 输出 draft/final/package
  -> 用户反馈修改
  -> 生成 revision plan
  -> 局部重跑并输出新版本
```

工程验收标准：

- `mag -v` 输出版本。
- 裸 `mag` 进入交互式 CLI。
- 空目录裸 `mag` 自动初始化 workspace。
- 非空非 workspace 裸 `mag` 中止并提示去空目录或显式 `mag init --force`。
- workspace 创建后存在 `.mag/workspace.json`、`.mag/state.json`、`.mag/config.toml`、`.env`、
  `input/`、`knowledge/`、`work/`、`output/`、`.git/`、`.gitignore`。
- `.env` 不进入 Git。
- 初始化后有初始 checkpoint commit。
- `/api` 能查看 required/recommended/optional API 状态。
- `/init` 能完成最小配置并写入 state。
- `/question`、`/data`、`/layout`、`/rag` 能复制文件到正确目录并记录 metadata。
- 未配置 LLM 时自然语言对话和 `/start` 会拦截。
- 题目未导入时 `/start` 会提示 `/question`。
- `/start` 能调用现有 workflow adapter，至少在 fake/demo provider 下端到端输出 draft/package。
- research script 锁定前有 data availability matrix。
- 修订循环至少支持用户反馈 -> revision plan -> 用户确认 -> 局部重跑或重新生成 draft。
- GitHub 自动 push 默认关闭，开启后 checkpoint 后 push，push 失败不阻断本地 workflow。
- `pytest -q` 和 `ruff check src tests` 通过。

## 3. 目标文件结构

新增或重点修改的文件：

| 文件 | 职责 |
|---|---|
| `install.sh` | 一键安装 `mag`。 |
| `src/mcm_agent/cli.py` | 保留 Typer 入口，裸 `mag` 进入 interactive session，高级命令继续可用。 |
| `src/mcm_agent/cli_session.py` | 交互式 shell 主循环、输入读取、状态摘要、自然语言路由。 |
| `src/mcm_agent/cli_commands/__init__.py` | slash command 注册表。 |
| `src/mcm_agent/cli_commands/base.py` | Slash command protocol、command result、prompt helper。 |
| `src/mcm_agent/cli_commands/api.py` | `/api`。 |
| `src/mcm_agent/cli_commands/init.py` | `/init`。 |
| `src/mcm_agent/cli_commands/imports.py` | `/question`、`/data`、`/layout`、`/rag`。 |
| `src/mcm_agent/cli_commands/git.py` | `/git`。 |
| `src/mcm_agent/cli_commands/start.py` | `/start`。 |
| `src/mcm_agent/cli_commands/status.py` | `/status`、`/outputs`、`/reset`。 |
| `src/mcm_agent/core/workspace.py` | 迁移到新 workspace layout，并兼容旧 workflow layout。 |
| `src/mcm_agent/core/workspace_models.py` | `WorkspaceMetadata`、`WorkspaceState`、`ImportedResource` 等 Pydantic model。 |
| `src/mcm_agent/core/workspace_safety.py` | Git init、`.gitignore`、checkpoint、dirty check、可选 push。 |
| `src/mcm_agent/core/events.py` | 扩展 typed event，支持 session/event log。 |
| `src/mcm_agent/core/session_store.py` | `.mag/chat/messages.jsonl`、sessions、summary。 |
| `src/mcm_agent/core/imports.py` | 文件复制、目录导入、metadata、冲突命名。 |
| `src/mcm_agent/core/research_script.py` | research script、data need、lock state。 |
| `src/mcm_agent/core/workflow_adapter.py` | 新 workspace layout 到现有 `run_mvp_workflow` 的适配。 |
| `src/mcm_agent/config.py` | 支持 workspace-local `.env` 和 `.mag/config.toml`。 |
| `src/mcm_agent/providers/github.py` | 可选 GitHub remote/push adapter；优先调用 Git CLI，后续可接 GitHub API。 |
| `tests/test_cli_interactive.py` | 裸 `mag`、交互输入、slash dispatch。 |
| `tests/test_workspace_v2.py` | 新 workspace layout。 |
| `tests/test_workspace_safety.py` | Git 安全网。 |
| `tests/test_cli_commands.py` | slash commands。 |
| `tests/test_import_commands.py` | question/data/layout/rag 导入。 |
| `tests/test_session_store.py` | 对话历史。 |
| `tests/test_workflow_adapter.py` | 新旧 workflow layout 适配。 |
| `tests/test_install_script.py` | 安装脚本静态和 smoke 检查。 |

旧的 `src/mcm_agent/server/` 继续保留，但不是当前实施主线。

## 4. 里程碑与任务

### M0：建立实施护栏

**目标：** 保证后续每个任务都能安全推进，避免一次性大改。

**Files:**

- Modify: `docs/dev/roadmap.md`
- Modify: `tests/test_docs.py`

**Steps:**

- [ ] 在 `tests/test_docs.py` 增加断言：`docs/dev/implementation-plan.md` 存在，并包含
  `Workspace Safety`、`/init`、`/start`、`GitHub 自动 push`、`research script`。
- [ ] 运行 `pytest tests/test_docs.py -q`，预期通过。
- [ ] 提交：`git commit -m "docs: add full implementation plan guardrails"`。

**验收：** 文档测试能保护实施计划不被误删。

### M1：一键安装与命令身份

**目标：** 用户从 GitHub 看到项目后能一条命令安装 `mag`。

**Files:**

- Create: `install.sh`
- Modify: `README.zh-CN.md`
- Modify: `README.md`
- Modify: `tests/test_install_script.py`
- Modify: `tests/test_cli_config.py`

**Steps:**

- [ ] 写测试：检查 `install.sh` 存在、可执行、包含 `set -euo pipefail`、安装目标是 `mag` 而不是
  `mcm-agent`。
- [ ] 实现 `install.sh`：检测 Python、优先使用 `pipx`，否则提示用户安装 `pipx` 或使用
  `python -m pip install --user .`。
- [ ] README 增加安装命令和安装后验证：`mag -v`。
- [ ] 运行：`pytest tests/test_install_script.py tests/test_cli_config.py -q`。
- [ ] 手动 smoke：`bash -n install.sh`。
- [ ] 提交：`git commit -m "feat: add mag install script"`。

**验收：** 安装路径清晰，项目对外身份完全是 `mag`。

### M2：Workspace v2 layout 与兼容层

**目标：** 创建设计文档规定的新 workspace 结构，同时不破坏现有 workflow。

**Files:**

- Create: `src/mcm_agent/core/workspace_models.py`
- Modify: `src/mcm_agent/core/workspace.py`
- Create: `tests/test_workspace_v2.py`
- Modify: `tests/test_workspace_registry.py`

**Steps:**

- [ ] 写测试：空目录调用 `create_workspace(path)` 后存在 `.mag/workspace.json`、`.mag/state.json`、
  `.mag/config.toml`、`.env`、`input/problem`、`input/data`、`input/layout`、`knowledge`、
  `work`、`output`。
- [ ] 定义 `WorkspaceMetadata`：`schema_version`、`workspace_id`、`created_at`、`updated_at`、
  `mag_version`、`status`。
- [ ] 定义 `WorkspaceState`：`init`、`phase`、`problem`、`last_stage`、`blocked_reason`、
  `resources`、`git`。
- [ ] 修改 `create_workspace`：创建新 layout，同时继续创建现有 workflow 所需目录或通过
  `work/legacy` 兼容。
- [ ] 增加 `is_mag_workspace(path)`：检查 `.mag/workspace.json` 和 `.mag/state.json`。
- [ ] 增加 `load_workspace_state`、`save_workspace_state`。
- [ ] 运行：`pytest tests/test_workspace_v2.py tests/test_workspace_registry.py -q`。
- [ ] 提交：`git commit -m "feat: add workspace v2 layout"`。

**验收：** 新 workspace contract 成立，旧测试不退化。

### M3：Git 安全网

**目标：** workspace 创建时默认有本地 Git checkpoint。

**Files:**

- Create: `src/mcm_agent/core/workspace_safety.py`
- Modify: `src/mcm_agent/core/workspace.py`
- Create: `tests/test_workspace_safety.py`

**Steps:**

- [ ] 写测试：初始化 workspace 后 `.git/` 存在。
- [ ] 写测试：`.gitignore` 包含 `.env`、`.mag/cache/`、`.mag/logs/*.debug.json`、`.DS_Store`。
- [ ] 写测试：`git log --oneline` 至少有 `mag workspace initialized`。
- [ ] 写测试：`.env` 不在 `git ls-files` 中。
- [ ] 实现 `WorkspaceSafety.ensure_git_repo(root)`。
- [ ] 实现 `WorkspaceSafety.ensure_gitignore(root)`。
- [ ] 实现 `WorkspaceSafety.checkpoint(root, message)`：无变化时不创建空 commit。
- [ ] 实现 `WorkspaceSafety.status(root)`：返回 clean/dirty、last_commit、remote、auto_push。
- [ ] 运行：`pytest tests/test_workspace_safety.py -q`。
- [ ] 提交：`git commit -m "feat: add workspace git safety net"`。

**验收：** 可以放心给 Agent 较高文件权限，因为每轮关键写入都有恢复点。

### M4：配置系统与 `/api`

**目标：** API key 写入 `.env`，非 secret 写入 `.mag/config.toml`，并能在 CLI 中查看状态。

**Files:**

- Modify: `src/mcm_agent/config.py`
- Create: `src/mcm_agent/cli_commands/base.py`
- Create: `src/mcm_agent/cli_commands/api.py`
- Create: `tests/test_cli_commands.py`
- Modify: `tests/test_config_merge.py`

**Steps:**

- [ ] 写测试：workspace-local `.env` 覆盖进 `load_settings`。
- [ ] 写测试：`.mag/config.toml` 可读取 LLM provider、model、search enabled、git auto_push。
- [ ] 写测试：`ApiCommand.render_status()` 输出 Required、Recommended、Optional 三组。
- [ ] 实现 workspace config loader：读取全局 env、workspace `.env`、`.mag/config.toml`。
- [ ] 实现 `/api` 只展示状态，不在测试里真实请求外部 API。
- [ ] 实现交互式配置 helper：隐藏输入 API key，写入 `.env`。
- [ ] 运行：`pytest tests/test_cli_commands.py tests/test_config_merge.py -q`。
- [ ] 提交：`git commit -m "feat: add workspace api configuration"`。

**验收：** LLM 是唯一 required；Search、arXiv、GitHub、数据库等可显示 missing/skipped/disabled。

### M5：交互式 CLI shell 和 slash command registry

**目标：** 裸 `mag` 进入交互式界面，`/` 命令可分发。

**Files:**

- Modify: `src/mcm_agent/cli.py`
- Create: `src/mcm_agent/cli_session.py`
- Create: `src/mcm_agent/cli_commands/__init__.py`
- Create: `src/mcm_agent/cli_commands/status.py`
- Create: `tests/test_cli_interactive.py`

**Steps:**

- [ ] 写测试：空目录执行 Typer runner `mag` 会初始化 workspace 并输出启动界面摘要。
- [ ] 写测试：非空非 workspace 执行裸 `mag` 会退出并提示在空文件夹运行。
- [ ] 写测试：已有 workspace 执行裸 `mag` 会加载 state 并显示恢复摘要。
- [ ] 写测试：输入 `/help` 显示命令列表。
- [ ] 实现 `InteractiveSession.run_once(input_text)` 便于测试，不依赖真实 stdin。
- [ ] 实现 command registry：`help`、`api`、`init`、`question`、`data`、`layout`、`rag`、
  `start`、`status`、`outputs`、`reset`、`git`。
- [ ] `cli.py` callback 在无子命令时进入 `InteractiveSession`。
- [ ] 保留 `mag init`、`mag inspect`、`mag run` 等高级命令。
- [ ] 运行：`pytest tests/test_cli_interactive.py tests/test_cli_config.py -q`。
- [ ] 提交：`git commit -m "feat: add interactive mag shell"`。

**验收：** 普通用户只需要输入 `mag`。

### M6：资源导入命令

**目标：** `/question`、`/data`、`/layout`、`/rag` 能复制文件并记录 metadata。

**Files:**

- Create: `src/mcm_agent/core/imports.py`
- Create: `src/mcm_agent/cli_commands/imports.py`
- Create: `tests/test_import_commands.py`

**Steps:**

- [ ] 写测试：`/question` 把 PDF 复制到 `input/problem/`，更新 `.mag/state.json`。
- [ ] 写测试：`/data` 支持文件和目录，复制到 `input/data/`。
- [ ] 写测试：`/layout` 复制模板到 `input/layout/`。
- [ ] 写测试：`/rag` 根据用户选择复制到 `knowledge/papers|methods|rules|cases`。
- [ ] 写测试：同名文件冲突时追加短 hash，不覆盖原文件。
- [ ] 实现 `copy_resource(source, target_dir, resource_type)`。
- [ ] 实现 `ImportedResource` metadata 写入 `.mag/resources.jsonl`。
- [ ] 每次导入完成后调用 `WorkspaceSafety.checkpoint`。
- [ ] 运行：`pytest tests/test_import_commands.py tests/test_workspace_safety.py -q`。
- [ ] 提交：`git commit -m "feat: add workspace import commands"`。

**验收：** 用户粘贴路径即可导入资料，所有导入都有 Git checkpoint。

### M7：`/init` 初始化向导

**目标：** 第一次 workspace 能完成最小必要配置；二次 `/init` 提供重新思考/完全重置。

**Files:**

- Create: `src/mcm_agent/cli_commands/init.py`
- Modify: `src/mcm_agent/core/workspace_models.py`
- Create: `tests/test_init_command.py`

**Steps:**

- [ ] 写测试：第一次 `/init` 要求 LLM 配置，Search/arXiv/GitHub 可跳过。
- [ ] 写测试：完成 `/init` 后 `state.init.completed == true`。
- [ ] 写测试：二次 `/init` 显示 Cancel、Re-think only、Full reset。
- [ ] 写测试：Re-think only 清理 `.mag/chat/`、`work/`、`output/`，保留 `.env`、input、knowledge。
- [ ] 写测试：Full reset 必须输入 `RESET`。
- [ ] 实现 `InitCommand` 的 step runner，测试中可注入 answers。
- [ ] 每个危险 reset 前调用 checkpoint。
- [ ] 运行：`pytest tests/test_init_command.py -q`。
- [ ] 提交：`git commit -m "feat: add init wizard"`。

**验收：** `/init` 既能引导新用户，也能安全重置老 workspace。

### M8：Session、事件流和上下文治理基础

**目标：** 每次对话和 command 都留下可恢复记录，为后续 daemon/TUI 留接口。

**Files:**

- Create: `src/mcm_agent/core/session_store.py`
- Modify: `src/mcm_agent/core/events.py`
- Modify: `src/mcm_agent/cli_session.py`
- Create: `tests/test_session_store.py`

**Steps:**

- [ ] 写测试：用户消息写入 `.mag/chat/messages.jsonl`。
- [ ] 写测试：assistant 消息写入 `.mag/chat/messages.jsonl`。
- [ ] 写测试：command 事件写入 `.mag/events.jsonl`。
- [ ] 写测试：超过水位后生成 `.mag/chat/summary.md`，但不删除原始 messages。
- [ ] 实现 `SessionStore.append_message`、`read_recent_messages`、`write_summary`。
- [ ] 实现 typed events：`CommandStarted`、`CommandFinished`、`AgentStageStarted`、
  `AgentStageFinished`、`GateFailed`、`CheckpointCreated`。
- [ ] 运行：`pytest tests/test_session_store.py -q`。
- [ ] 提交：`git commit -m "feat: add session and event store"`。

**验收：** 执行过程不是黑盒，后续可接 TUI 或 trace 回放。

### M9：自然语言守卫和 LLM 对话最小闭环

**目标：** 用户未完成必要条件时被正确引导；满足条件后能与 LLM 讨论。

**Files:**

- Modify: `src/mcm_agent/cli_session.py`
- Create: `src/mcm_agent/core/dialogue_guard.py`
- Create: `tests/test_dialogue_guard.py`

**Steps:**

- [ ] 写测试：未配置 LLM 时输入普通文本，提示配置 `/api`。
- [ ] 写测试：未导入题目时输入“分析题目”，提示 `/question`。
- [ ] 写测试：缺 Search/arXiv 只提示不阻断。
- [ ] 写测试：满足 LLM + question 后普通文本进入 provider fake LLM。
- [ ] 实现 `DialogueGuard.evaluate(state, message)`。
- [ ] 实现 fake LLM conversation adapter，不调用真实外部 API。
- [ ] 运行：`pytest tests/test_dialogue_guard.py tests/test_llm_agents.py -q`。
- [ ] 提交：`git commit -m "feat: add dialogue guard"`。

**验收：** 用户不会在缺必要配置时得到神秘失败。

### M10：Research script 与数据可得性锁定

**目标：** `/start` 后先讨论和检查数据，再锁定最终论文脚本。

**Files:**

- Create: `src/mcm_agent/core/research_script.py`
- Create: `src/mcm_agent/cli_commands/start.py`
- Modify: `src/mcm_agent/agents/data_feasibility.py`
- Modify: `src/mcm_agent/agents/discussion.py`
- Create: `tests/test_research_script.py`
- Modify: `tests/test_data_feasibility.py`
- Modify: `tests/test_discussion_data_loop.py`

**Steps:**

- [ ] 写测试：`/start` 缺 LLM 阻断。
- [ ] 写测试：`/start` 缺 question 阻断。
- [ ] 写测试：生成 `work/discussion/research_script_draft.md/json`。
- [ ] 写测试：每个 data need 有 available、needs_api、manual_upload、replace_plan 之一。
- [ ] 写测试：用户确认后写入 `locked_research_script.md/json`。
- [ ] 实现 `ResearchScript`、`DataNeed`、`DataAvailabilityMatrix`。
- [ ] 将现有 data feasibility agent 输出适配到 `DataAvailabilityMatrix`。
- [ ] 用户确认 lock 后创建 checkpoint。
- [ ] 运行：`pytest tests/test_research_script.py tests/test_data_feasibility.py -q`。
- [ ] 提交：`git commit -m "feat: add research script locking"`。

**验收：** Mag 不会在数据不可得时硬写论文。

### M11：Workflow adapter 接入现有自动实现

**目标：** locked research script 后复用现有 workflow 引擎生成论文产物。

**Files:**

- Create: `src/mcm_agent/core/workflow_adapter.py`
- Modify: `src/mcm_agent/cli_commands/start.py`
- Modify: `src/mcm_agent/workflows/mvp.py`
- Create: `tests/test_workflow_adapter.py`
- Modify: `tests/test_mvp_workflow.py`

**Steps:**

- [ ] 写测试：从 workspace v2 读取 problem/data/layout，构建现有 `TaskInput`。
- [ ] 写测试：workflow 输出从旧目录映射到 `work/` 和 `output/`。
- [ ] 写测试：fake provider 下 `/start` 可以跑到 draft/package。
- [ ] 实现 `WorkspaceWorkflowAdapter.to_task_input`。
- [ ] 实现 `WorkspaceWorkflowAdapter.sync_outputs`。
- [ ] 在 stage start/finish 写入 event log。
- [ ] 每个主要阶段完成后创建 checkpoint。
- [ ] 运行：`pytest tests/test_workflow_adapter.py tests/test_mvp_workflow.py -q`。
- [ ] 提交：`git commit -m "feat: connect interactive start to workflow"`。

**验收：** 新 CLI 入口能复用现有底层 agent workflow。

### M12：进度展示、status、inspect 和 outputs

**目标：** 用户看到人类可读进度，开发者能看到底层 stage/gate。

**Files:**

- Modify: `src/mcm_agent/cli_commands/status.py`
- Modify: `src/mcm_agent/cli.py`
- Modify: `src/mcm_agent/core/events.py`
- Create: `tests/test_status_outputs.py`

**Steps:**

- [ ] 写测试：`/status` 显示 init、problem、data、rag、phase、last checkpoint。
- [ ] 写测试：`/outputs` 显示 draft/final/package 路径。
- [ ] 写测试：`mag inspect` 能读取 v2 workspace，并继续支持旧 task_state。
- [ ] 实现用户可读 stage 文案：正在理解题目、正在检查数据、正在运行模型、正在写论文。
- [ ] 运行：`pytest tests/test_status_outputs.py tests/test_cli_config.py -q`。
- [ ] 提交：`git commit -m "feat: add workspace status outputs"`。

**验收：** CLI 不暴露过多内部 stage，但调试入口足够清楚。

### M13：审查与修订循环

**目标：** 用户看完论文后能自然语言提出修改，Agent 先生成 revision plan，再执行。

**Files:**

- Modify: `src/mcm_agent/agents/revision.py`
- Create: `src/mcm_agent/core/revision_plan.py`
- Create: `src/mcm_agent/cli_commands/revision.py`
- Modify: `src/mcm_agent/cli_session.py`
- Create: `tests/test_revision_loop.py`
- Modify: `tests/test_reviewer_revision.py`

**Steps:**

- [ ] 写测试：draft 存在后用户自然语言反馈会生成 `work/revisions/revision_001.md/json`。
- [ ] 写测试：revision plan 包含 affected_sections、stages_to_rerun、expected_outputs。
- [ ] 写测试：用户确认前不修改论文。
- [ ] 写测试：用户确认后只重跑必要阶段，或在不确定时重跑 paper/review/package。
- [ ] 实现 `RevisionPlan` model。
- [ ] 实现 revision command handler。
- [ ] 每次修订输出到 `output/draft/revision_XXX/`。
- [ ] 运行：`pytest tests/test_revision_loop.py tests/test_reviewer_revision.py -q`。
- [ ] 提交：`git commit -m "feat: add revision loop"`。

**验收：** 修改论文是可审计循环，不是直接覆盖。

### M14：GitHub 自动 push

**目标：** 用户可选把 checkpoint 同步到 GitHub。

**Files:**

- Create: `src/mcm_agent/providers/github.py`
- Modify: `src/mcm_agent/core/workspace_safety.py`
- Modify: `src/mcm_agent/cli_commands/git.py`
- Create: `tests/test_github_sync.py`

**Steps:**

- [ ] 写测试：默认 `auto_push == false`。
- [ ] 写测试：开启 auto_push 但无 remote 时 `/git` 提示配置 remote。
- [ ] 写测试：checkpoint 后调用 injected push adapter。
- [ ] 写测试：push 失败记录 `.mag/logs/git_push_history.jsonl`，不回滚本地 commit。
- [ ] 实现 `GitHubSyncConfig`。
- [ ] 实现 `GitPushAdapter.push(remote, branch)`，测试中 fake。
- [ ] `/git` 支持显示状态、开启/关闭 auto push、记录最近错误。
- [ ] 运行：`pytest tests/test_github_sync.py tests/test_workspace_safety.py -q`。
- [ ] 提交：`git commit -m "feat: add optional github checkpoint sync"`。

**验收：** 用户可选择云端备份，但不会默认泄露 workspace。

### M15：RAG v2 与导入向导打通

**目标：** `/rag` 导入后能进入现有 RAG index，并在 discussion/modeling/writing 中检索使用。

**Files:**

- Modify: `src/mcm_agent/agents/rag.py`
- Modify: `src/mcm_agent/core/vector_index.py`
- Modify: `src/mcm_agent/cli_commands/imports.py`
- Modify: `tests/test_rag.py`
- Modify: `tests/test_hybrid_search.py`

**Steps:**

- [ ] 写测试：`/rag` 导入 PDF/Markdown 后生成 metadata。
- [ ] 写测试：无 embedding provider 时退化为关键词/FTS。
- [ ] 写测试：有 fake embedding provider 时写入 vector index。
- [ ] 写测试：discussion 阶段可读取 top-k RAG hits。
- [ ] 实现导入后异步或同步 indexing 策略；第一版使用同步 indexing，失败时记录 skipped reason。
- [ ] 运行：`pytest tests/test_rag.py tests/test_hybrid_search.py -q`。
- [ ] 提交：`git commit -m "feat: connect rag imports to retrieval"`。

**验收：** 用户导入的优秀论文、方法、规则能真正影响研究讨论和写作。

### M16：权限策略和高风险操作保护

**目标：** 高权限 Agent 运行前有可解释的安全策略。

**Files:**

- Create: `src/mcm_agent/core/permissions.py`
- Modify: `src/mcm_agent/core/workspace_safety.py`
- Modify: `src/mcm_agent/cli_session.py`
- Create: `tests/test_permissions.py`

**Steps:**

- [ ] 写测试：删除 `.env` 需要显式确认。
- [ ] 写测试：批量删除 `input/` 或 `knowledge/` 需要确认。
- [ ] 写测试：写入 `work/` 和 `output/` 可自动批准。
- [ ] 写测试：auto_approve 只影响低风险操作。
- [ ] 实现 `OperationRisk`：low、medium、high、blocked。
- [ ] 实现 `PermissionPolicy.evaluate(path, operation)`。
- [ ] 高风险操作前调用 checkpoint。
- [ ] 运行：`pytest tests/test_permissions.py tests/test_workspace_safety.py -q`。
- [ ] 提交：`git commit -m "feat: add workspace permission policy"`。

**验收：** 不是“因为有 Git 所以什么都能删”，而是 Git + policy 双保险。

### M17：发布前端到端验收

**目标：** 用 fake provider 和一个小型 demo 题目跑完整 CLI 流程。

**Files:**

- Create: `examples/demo_problem/problem.md`
- Create: `examples/demo_problem/data/sample.csv`
- Create: `scripts/run_cli_smoke.py`
- Create: `tests/test_cli_e2e.py`
- Modify: `README.zh-CN.md`

**Steps:**

- [ ] 写测试：`scripts/run_cli_smoke.py --tmp` 能创建 workspace、导入 demo、运行 fake workflow。
- [ ] 写 demo problem 和 sample data。
- [ ] 实现 CLI smoke script，用 subprocess 调 `mag` 高级命令或 session test harness。
- [ ] README 增加 demo 运行方式。
- [ ] 运行：`pytest tests/test_cli_e2e.py -q`。
- [ ] 运行：`python scripts/run_cli_smoke.py --tmp`。
- [ ] 提交：`git commit -m "test: add cli end-to-end smoke"`。

**验收：** 新贡献者能一条命令验证 Mag 真的可以跑通。

### M18：文档同步和英文文档准备

**目标：** 代码实现和中文文档保持一致，英文只做发布前准备。

**Files:**

- Modify: `README.zh-CN.md`
- Modify: `design.md`
- Modify: `docs/*.md`
- Modify: `docs/dev/*.md`
- Modify: `tests/test_docs.py`

**Steps:**

- [ ] 更新 README 的安装、初始化、demo、Git 安全网说明。
- [ ] 更新 `design.md` 中已经落地和仍待做的状态。
- [ ] 更新模块地图，加入新增文件职责。
- [ ] 更新测试指南，加入 CLI e2e 和 Git safety 测试。
- [ ] 增加文档测试：所有关键命令、关键文件、关键安全约束都被文档提到。
- [ ] 运行：`pytest tests/test_docs.py -q`。
- [ ] 提交：`git commit -m "docs: sync cli-first implementation docs"`。

**验收：** 文档不再只是愿景，而是准确反映实现。

### M19：后续可选 runtime 演进

**目标：** 在 CLI-first 成熟后，按 KamaClaude/OpenCode/Goose 的方向增加更强 runtime。

**Files:**

- Create: `src/mcm_agent/runtime/protocol.py`
- Create: `src/mcm_agent/runtime/event_bus.py`
- Create: `src/mcm_agent/runtime/daemon.py`
- Create: `src/mcm_agent/runtime/client.py`
- Create: `tests/test_runtime_protocol.py`

**Steps:**

- [ ] 抽出 typed event protocol，不改变现有 CLI 行为。
- [ ] 建立 NDJSON event stream，但先只在本进程中使用。
- [ ] 增加 daemon proof-of-concept：`mag daemon start`。
- [ ] 让 CLI 仍可单进程运行，daemon 是 opt-in。
- [ ] 后续再考虑 TUI/Web 客户端。

**验收：** runtime 演进不会阻塞 P0-P18 的 CLI-first 产品化。

## 5. 推荐执行顺序

必须串行：

```text
M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M9 -> M10 -> M11 -> M13 -> M17
```

可并行：

- M8 可以在 M5 后并行。
- M12 可以在 M11 后并行。
- M14 可以在 M3/M4 后并行。
- M15 可以在 M6 后并行。
- M16 可以在 M3 后并行。
- M18 每完成 2-3 个里程碑同步一次。
- M19 等 CLI-first 成熟后再做。

每个里程碑完成标准：

```bash
pytest -q
ruff check src tests
```

每个里程碑都应单独提交，commit message 使用：

```text
feat: ...
test: ...
docs: ...
refactor: ...
```

## 6. 风险清单

| 风险 | 应对 |
|---|---|
| 新 workspace layout 与现有 workflow layout 不一致 | 用 `workflow_adapter.py` 做边界，不把旧 workflow 直接改到不可测试。 |
| 交互式 CLI 难测试 | 所有 command 都提供可注入 input/output 的 `run_once` 或 command handler。 |
| Git checkpoint 可能提交敏感文件 | `.gitignore` 测试 + `git ls-files` 测试必须覆盖 `.env`。 |
| GitHub push 泄露隐私 | 默认关闭；开启前提示；失败不阻断本地流程。 |
| RAG/搜索/API 配置太复杂 | `/init` 只强制 LLM，其余按需提示。 |
| LLM 不稳定导致测试脆弱 | 单元测试默认 fake provider；真实 provider 只放 smoke。 |
| 过早 daemon 化 | M19 后置，前 18 个里程碑只做单进程 CLI。 |

## 7. 最小可发布版本

第一个可发布版本不需要完成所有高级能力，但必须完成：

- M1：一键安装。
- M2：workspace v2。
- M3：Git 安全网。
- M4：配置系统和 `/api`。
- M5：裸 `mag` 交互式 shell。
- M6：资源导入。
- M7：`/init`。
- M9：自然语言守卫。
- M10：research script 和数据可得性。
- M11：workflow adapter。
- M17：端到端 smoke。
- M18：文档同步。

M13 修订循环、M14 GitHub push、M15 RAG 深度打通、M16 权限策略可以作为 v0.2 增强，但设计上
必须提前留好接口。
