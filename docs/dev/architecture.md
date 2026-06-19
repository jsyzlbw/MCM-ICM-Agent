# 开发者架构说明

## 1. 代码总体分层

当前代码位于 `src/mcm_agent/`，可以按以下层理解：

```text
CLI / Server
  -> Workspace Safety
  -> Workflow Orchestration
  -> Agents
  -> Core Domain Models
  -> Providers
  -> Solver Modules
  -> Templates / Utilities
```

## 2. CLI 层

入口：

```text
src/mcm_agent/cli.py
```

职责：

- 暴露 `mag` 命令。
- 读取配置。
- 构建 provider bundle。
- 调用 workflow。
- 提供 inspect、resume、provider smoke 等开发者命令。

未来目标：

- 裸 `mag` 启动交互式 Agent。
- slash command 系统从 CLI 层进入。
- 传统参数命令保留为高级调试入口。

## 3. Workspace Safety 层

Workspace safety 是 CLI 和 workflow 之间的保护层。它不负责建模，而是负责让高权限 Agent 的
文件操作可恢复。

职责：

- workspace 创建时执行 `git init`。
- 创建和维护 `.gitignore`。
- 初始化后创建第一个 checkpoint commit。
- Agent 完成有意义修改后创建 checkpoint commit。
- 高风险文件操作前检查是否有未提交改动。
- 在用户显式开启后执行 GitHub 自动 push。
- 记录 push 失败、未提交修改和恢复提示。

未来可以把这部分放入 `src/mcm_agent/core/workspace_safety.py` 或类似模块，CLI 和 workflow
都通过它创建 checkpoint，而不是直接调用 `git`。

## 4. Workflow 层

入口：

```text
src/mcm_agent/workflows/mvp.py
src/mcm_agent/core/stage_executor.py
src/mcm_agent/core/workflow_graph.py
```

职责：

- 定义 stage handler。
- 按 workflow graph 执行阶段。
- 根据 gate decision 路由 repair stage。
- 写入 stage log 和 task state。

关键点：

- Stage 之间不共享隐藏上下文。
- Stage 通过 workspace 文件交换信息。
- Gate 失败后要明确 repair route。

## 5. Agents 层

目录：

```text
src/mcm_agent/agents/
```

职责：

- 每个文件对应一个或几个具体 Agent。
- Agent 读取 workspace artifacts。
- Agent 写入新的 reports、JSON、LaTeX、figure 或 review 文件。

开发规则：

- Agent 不应该直接依赖其他 Agent 的内存。
- Agent 输出必须能被测试读取。
- 关键输出要有机器可读 JSON。
- 重要失败要写入 gate 或 blocker，而不是只打印日志。

## 6. Core 层

目录：

```text
src/mcm_agent/core/
```

职责：

- Pydantic domain models。
- workflow graph。
- workspace 初始化。
- workspace Git checkpoint。
- gate decision。
- artifact registry。
- evidence、source、figure、claim 等基础结构。
- vector index、embedding cache 等跨模块能力。

开发规则：

- Core 层尽量不依赖具体 provider。
- Core 层类型应该稳定，因为很多 Agent 会使用。
- 新增跨 Agent contract 时，应优先放 core。

## 7. Providers 层

目录：

```text
src/mcm_agent/providers/
```

职责：

- LLM provider。
- Search provider。
- MinerU provider。
- Official data provider。
- Humanizer provider。
- LaTeX provider。
- Embedding/rerank provider。
- Provider smoke。
- GitHub 远端同步可以作为可选 provider 或 workspace safety adapter 处理。

开发规则：

- provider 必须能 fake。
- 测试默认不能依赖真实 API。
- 错误信息要脱敏。
- provider 失败不能随意让整个 workflow 崩掉，除非它是当前阶段的硬依赖。

## 8. Solver Modules

目录：

```text
src/mcm_agent/solver_modules/
```

职责：

- 提供确定性 baseline solver。
- 支持 evaluation、optimization、forecasting、simulation、classification、clustering、
  queueing、network 等路线。

开发规则：

- 输入输出要稳定。
- 随机过程要有 seed。
- 结果必须能进入 evidence registry。

## 9. Server 层

目录：

```text
src/mcm_agent/server/
```

当前已有本地 GUI API。长期方向是 CLI-first，因此 server 层不是当前产品主入口，但仍可保留：

- 配置 API。
- workspace API。
- workflow control API。
- knowledge base API。
- artifacts API。

如果之后 CLI-first 成熟，server 可以作为可选本地面板，而不是主产品路径。

## 10. Templates

目录：

```text
src/mcm_agent/templates/
```

职责：

- LLM prompts。
- LaTeX Jinja templates。

开发规则：

- prompt 改动要配测试。
- LaTeX 模板改动要跑 typesetting 相关测试。

## 11. 测试分层

测试在 `tests/`：

- CLI 行为测试。
- config merge 测试。
- provider fake/smoke 测试。
- RAG 测试。
- workflow 测试。
- workspace safety 和 Git checkpoint 测试。
- agent 单元测试。
- solver module 测试。
- paper/review/submission 测试。

新增功能优先写行为测试，不要只测内部实现细节。
