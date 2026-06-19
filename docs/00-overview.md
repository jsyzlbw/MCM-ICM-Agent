# 00. 项目总览

## 1. Mag 是什么

Mag 是一个本地命令行数学建模 Agent，目标用户是参加 MCM/ICM 或类似数学建模竞赛的人。
它不是普通聊天机器人，也不是单次脚本生成器，而是一个可持续工作的本地 workspace：

```text
题目与数据
  -> 讨论研究方向
  -> 检查数据可得性
  -> 锁定研究脚本
  -> 建模与求解
  -> 图表与论文
  -> 审查与修订
  -> 提交包
```

Mag 通过命令行运行。用户在赛题文件夹输入 `mag`，进入类似 Claude Code / Codex CLI 的
交互界面。用户可以自然语言交流，也可以通过 slash command 执行明确操作。

## 2. 项目的两个视角

### 用户视角

用户关心：

- 怎么安装 `mag`。
- 怎么导入题目、数据、模板。
- 怎么配置必要 API。
- 怎么让 Agent 分析题目。
- 怎么和 Agent 讨论研究方向。
- 怎么得到论文和提交包。
- 怎么继续修改论文。

### 开发者视角

开发者关心：

- CLI 如何启动。
- workspace 如何组织。
- Agent 阶段如何串联。
- provider 如何配置和调用。
- RAG 如何导入和检索。
- 数据可得性如何判断。
- 论文证据链如何维护。
- gate 失败后如何修复。
- 哪些测试保护哪些行为。

本文档系统用 `README.zh-CN.md` 做入口，用 `design.md` 讲产品目标，用 `docs/` 讲模块设计，
用 `docs/dev/` 讲开发者实现细节。

## 3. 核心概念

### 3.1 Workspace

Workspace 是一次建模任务的本地工作区。它包含：

- 用户导入的题目。
- 用户导入的数据。
- 用户导入的论文模板。
- 用户导入的 RAG 资料。
- Agent 的对话历史。
- 中间报告。
- 数据来源日志。
- 模型结果。
- 证据注册表。
- 图表。
- LaTeX 论文。
- review 报告。
- 最终提交包。

Workspace 是 Mag 的状态边界。用户下次在同一个文件夹输入 `mag`，Mag 应该恢复之前的工作。

Workspace 也是 Mag 的安全边界。创建 workspace 时必须默认创建本地 Git 仓库，并在初始化后写入
第一个 checkpoint commit。之后 Agent 每轮完成有意义的修改，都应该形成可恢复的 checkpoint。
这样即使 Agent 获得较高文件权限，也可以通过 Git 历史找回被误删或误改的内容。GitHub 远端
同步是可选能力，只有用户显式开启后才自动 push。

### 3.2 Slash Command

Slash command 是以 `/` 开头的操作命令，例如：

- `/api`
- `/rag`
- `/question`
- `/data`
- `/layout`
- `/init`
- `/start`

Slash command 负责明确动作，自然语言负责讨论。

### 3.3 Research Script

Research script 是“最终论文脚本”。它不是代码脚本，而是论文和建模工作的执行蓝图，包含：

- 子问题拆解。
- 模型选择。
- 数据需求。
- 数据可得性判断。
- 指标体系。
- 求解方法。
- 图表计划。
- 论文结构。
- 风险和备选方案。

Agent 只有在用户确认 research script 后，才应该进入自动实现阶段。

### 3.4 Evidence Registry

Evidence registry 是论文证据注册表。论文中的关键结论、数字、图表和外部事实都应能追溯到：

- 题目原文。
- 用户上传数据。
- 外部来源。
- 代码运行结果。
- 用户确认的假设。

没有证据的关键 claim 不应该直接写入最终论文。

### 3.5 Gate

Gate 是阶段性质量检查。例如：

- extraction gate：题目抽取是否完整。
- modeling gate：模型计划是否可执行。
- source gate：数据来源是否可靠。
- validation gate：结果是否可信。
- figure gate：图表是否可用。
- final gate：是否可以打包提交。

Gate 失败后应进入明确的 repair route，而不是继续生成看似完整但不可审计的论文。

## 4. 当前实现状态

CLI-first 产品形态已经落地，并用 2026 MCM Problem C 真题端到端验证（真实 LLM + tectonic）。

底层结构：

- `src/mcm_agent/cli.py`：Typer 入口，裸 `mag` 进入交互式 session。
- `src/mcm_agent/cli_session.py` + `src/mcm_agent/cli_commands/`：交互 shell、slash 命令、自然语言对话。
- `src/mcm_agent/workflows/mvp.py` / `core/stage_executor.py` / `core/workflow_graph.py`：workflow 组装、stage 执行、拓扑。
- `src/mcm_agent/agents/`：各阶段 Agent。
- `src/mcm_agent/providers/` + `core/workflow_adapter.py`：真实 provider 构建与接入。
- `src/mcm_agent/solver_modules/`：确定性 solver baseline（LLM 代码生成失败时的兜底）。
- `tests/`：覆盖 CLI、workflow、provider、RAG、solver、paper、server 等行为。

三个产品化阶段已完成（均在 main、真题验证）：

- **阶段 1 真实 provider 端到端**：交互式 CLI 用真实配置构建 provider 跑出可编译 PDF；可选 provider 失败降级；`LatexProvider` 自动探测 tectonic；中文论文用 ctexart 不丢字。
- **阶段 2 智能内核**：`SolverCoderAgent` 让 LLM 针对真实数据生成并执行题目专属 Python（自修复 + baseline 兜底），真实指标进入证据链与论文 Results。
- **阶段 3 对话式 CLI**：自然语言接真实 LLM（跟随用户语言）；`/start --language` 把论文语言贯通到写作；运行时显示人类可读进度。

成熟度增强：API key 在对话日志中脱敏；剥离 LLM 输出寒暄前言；语言感知、限长摘要；`/api`、`/status` 反映真实配置。详见 `docs/superpowers/specs/` 与 `docs/superpowers/plans/`。

## 5. 文档地图

| 文档 | 读者 | 解决的问题 |
|---|---|---|
| `README.zh-CN.md` | 所有人 | 项目是什么、从哪里开始读。 |
| `design.md` | 产品和架构读者 | Mag 最终目标产品形态。 |
| `docs/01-cli-product-design.md` | CLI 开发者 | `mag` 交互界面和命令。 |
| `docs/02-workspace-design.md` | 核心开发者 | workspace 文件结构和状态。 |
| `docs/03-agent-workflow-design.md` | Agent 开发者 | 阶段、gate、repair。 |
| `docs/04-provider-design.md` | provider 开发者 | API 配置和延迟启用策略。 |
| `docs/05-rag-design.md` | RAG 开发者 | 文档导入、索引、使用边界。 |
| `docs/06-paper-generation-design.md` | 写作链路开发者 | 建模、证据、图表和论文。 |
| `docs/07-review-and-revision-design.md` | 修订链路开发者 | 用户反馈和循环修改。 |
| `docs/dev/*` | 贡献者 | 如何读代码、测试、贡献。 |
