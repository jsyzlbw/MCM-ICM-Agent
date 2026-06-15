# MCM/ICM Agent GUI 产品化设计文档

## 1. 目标

将当前 CLI-first 的 MCM/ICM Agent 产品化为本地优先的 GUI 应用，让普通用户可以通过浏览器完成配置、范文导入、题目上传、方案讨论、自动建模写作、过程观察、结果审核和修改反馈。

本设计不重写现有 agent 内核。现有 `mcm_agent` 工作流、workspace artifacts、JSON 配置、RAG、provider、gate、review、LaTeX QA/repair 和 submission package 继续作为核心能力。GUI 层通过服务 API 调用这些能力，并把运行过程转化为用户可理解的状态、事件、文件预览和审批动作。

## 2. 产品原则

1. **本地优先**：第一版运行在用户本机，避免一开始引入账号、多用户、云存储、计费和权限系统。
2. **不隐藏过程**：用户必须能看到 agent 正在做什么、卡在哪里、生成了什么 artifact。
3. **用户可干预**：关键节点支持用户确认、修改、追问、重新生成、跳过或终止。
4. **配置安全**：API key 存在本地 `mcm_agent_config.local.json`，该文件被 git 忽略。GUI 不明文回显完整 key。
5. **结构化知识库**：范文不是随便上传的文件，而是按 case 组织，保留题目、数据、论文、笔记和元数据。
6. **复用工作流内核**：GUI 不绕过现有 gate 和 evidence governance，而是让用户更容易使用它们。
7. **渐进交付**：先完成 API 化和运行可视化，再扩展 HIL、结构化 RAG、多模态和修改闭环。

## 3. 目标用户流程

完整目标流程如下：

```text
用户配置 API
        ↓
用户导入优秀范文知识库
        ↓
用户创建本次任务并上传题目、数据、模板、额外要求
        ↓
用户点击“开始思考”
        ↓
agent 解析题目、检索范文、识别数据需求、提出实施方案草案
        ↓
用户与 agent 讨论并修改方案
        ↓
用户确认方案
        ↓
agent 执行多阶段建模工作流，生成代码、结果、图、LaTeX 和 PDF
        ↓
用户审核论文、图表、结果和 review 报告
        ↓
用户用自然语言提出修改意见
        ↓
agent 判断修复 stage，局部重跑并更新论文
        ↓
用户确认后导出最终 submission package
```

## 4. GUI 主模块

### 4.1 设置页

设置页管理所有 runtime provider 配置。第一版直接读写 `mcm_agent_config.local.json`。

需要支持的配置区块：

- `llm`：默认 LLM provider、base URL、model、API key、timeout。
- `search`：Tavily、Firecrawl、Brave、Exa。
- `official_data`：FRED、US Census、NOAA，以及 World Bank、OECD、UNData、NASA POWER、Open-Meteo、OSM/Overpass 的 base URL。
- `mineru`：fake、local、REST 模式，CLI 路径、REST API key。
- `humanizer`：UShallPass 或 fake。
- `rag`：知识库根目录、可 ingest 后缀。
- `runtime`：默认语言、最大重试、HTTP timeout、代码执行 timeout。

交互要求：

- API key 输入框保存后只显示“已配置”或末尾 4 位，不显示完整 key。
- 支持“一键 Provider Smoke”，调用现有 provider smoke 能力，返回 passed、skipped、failed。
- 支持恢复默认配置，但不会删除已填写 key，除非用户明确点击清空。

### 4.2 RAG 范文知识库页

知识库页用于导入和管理优秀数学建模范文。要求用户按 case 上传，而不是散装上传文件。

推荐目录结构：

```text
knowledge_base/
  cases/
    2024_mcm_c_momentum_finalist/
      metadata.json
      problem/
        problem.pdf
      data/
        Wimbledon_featured_matches.csv
      paper/
        finalist_paper.pdf
      notes/
        method_notes.md
```

`metadata.json` 结构：

```json
{
  "case_id": "2024_mcm_c_momentum_finalist",
  "contest": "MCM",
  "year": 2024,
  "problem": "C",
  "award": "Finalist",
  "language": "en",
  "methods": ["momentum model", "logistic regression", "Markov chain"],
  "tags": ["sports", "time series", "classification"]
}
```

校验规则：

- 每个 case 必须有 `metadata.json`。
- 每个 case 必须有 `problem/` 且至少包含一个题目文件。
- 每个 case 必须有 `paper/` 且至少包含一篇论文。
- `data/` 可为空，因为部分题目没有官方数据。
- `notes/` 可为空，用于用户补充方法点评、获奖经验、论文结构分析。

GUI 功能：

- 上传 case zip 或选择本地 case 文件夹。
- 显示 case 完整度：complete、incomplete、invalid。
- 显示已 ingest 的 chunk 数、方法标签、来源文件。
- 支持重新 ingest 单个 case 或整个知识库。
- 支持打开 case 文件列表和 metadata。

### 4.3 本次题目上传区

题目上传区用于创建一次新的建模任务。不能假设题目只有一个 PDF。

用户可上传：

- 题目文件：PDF、Markdown、TXT、DOCX、图片。
- 附件数据：CSV、XLSX、JSON、PDF、ZIP。
- 格式样例：LaTeX 模板、PDF 样例、Word 样例、竞赛规则。
- 其他要求：用户可以输入自然语言，例如“优先使用可解释模型”“论文用英文”“不要使用过于复杂的深度学习”。

workspace 目标结构：

```text
input/
  problem/
  attachments/
  template/
  user_requirements.md
```

后端需要将这些输入转换为现有 `TaskInput` 可消费的形式。第一版可以保持 `TaskInput.problem_file` 为主问题文件，同时把其他题目文件作为 attachments 传入；后续再扩展为多 problem files 的正式模型。

### 4.4 对话区

对话区是用户与 agent 协作的主界面。

对话能力：

- 用户可自然语言描述偏好、约束、修改意见。
- 用户可上传文件或图片作为消息附件。
- agent 回复应绑定当前 workspace，不做无上下文闲聊。
- 重要讨论结论写入 `discussion/` artifacts。

核心用途：

- 开始前讨论题目理解。
- 修改 agent 提出的实施方案。
- 审核中指出不满意之处。
- 让 agent 解释某个结果、图表、数据来源或审稿问题。

第一版可以将对话实现为 workspace-scoped message log：

```text
discussion/chat_messages.jsonl
```

消息结构：

```json
{
  "message_id": "msg_001",
  "timestamp": "2026-06-15T12:00:00Z",
  "role": "user",
  "content": "第三问希望增加敏感性分析。",
  "attachments": ["input/chat_uploads/image_001.png"]
}
```

### 4.5 Agent Activity 运行观察区

运行观察区解决“用户不知道是不是卡住了”的问题。

应展示：

- 当前 stage。
- 每个 stage 的状态：pending、running、passed、failed、waiting_user、skipped。
- 当前 agent 名称。
- 最近事件流。
- 生成中的 artifact。
- gate 阻塞原因。
- checkpoint 审批卡片。
- 运行时长和最近一次事件时间。

新增统一进度 artifact：

```text
progress_events.jsonl
```

事件结构：

```json
{
  "event_id": "evt_001",
  "timestamp": "2026-06-15T12:00:00Z",
  "workspace_id": "task_001",
  "stage_id": "problem_understanding",
  "agent": "ProblemUnderstandingAgent",
  "level": "info",
  "status": "running",
  "message": "Analyzing objectives, constraints, and available data.",
  "artifact_paths": ["reports/problem_understanding.md"]
}
```

第一版 GUI 可通过轮询读取事件。后续可升级为 Server-Sent Events 或 WebSocket。

### 4.6 Artifact 预览区

用户需要直接看到结果，而不是去文件夹里找。

预览对象：

- Markdown reports。
- JSON gate/review 文件。
- 图表 SVG/PNG/PDF。
- `paper/main.tex`。
- `paper/main.pdf`。
- `final_submission/submission_package.zip` 下载入口。

第一版可以用简单 tab 预览：

```text
Overview | Reports | Figures | Paper PDF | LaTeX | Review | Files
```

## 5. 后端服务设计

新增服务层：

```text
src/mcm_agent/server/
  app.py
  schemas.py
  routes_config.py
  routes_knowledge.py
  routes_workspace.py
  routes_chat.py
  routes_events.py
  routes_artifacts.py
  background.py
```

### 5.1 启动命令

新增 CLI 命令：

```bash
mcm-agent gui
```

行为：

- 启动 FastAPI 后端。
- 输出本地 URL，例如 `http://localhost:8787`。
- 第一版前端可由单独 dev server 运行；打包后可由 FastAPI 静态托管。

### 5.2 API 草案

配置：

```text
GET  /api/config
POST /api/config
POST /api/config/smoke
```

知识库：

```text
GET  /api/knowledge/cases
POST /api/knowledge/cases
POST /api/knowledge/cases/upload-zip
POST /api/knowledge/cases/{case_id}/ingest
POST /api/knowledge/ingest-all
GET  /api/knowledge/status
```

workspace：

```text
POST /api/workspaces
GET  /api/workspaces
GET  /api/workspaces/{workspace_id}
POST /api/workspaces/{workspace_id}/files
POST /api/workspaces/{workspace_id}/run
POST /api/workspaces/{workspace_id}/resume
POST /api/workspaces/{workspace_id}/stop
GET  /api/workspaces/{workspace_id}/status
```

对话：

```text
GET  /api/workspaces/{workspace_id}/messages
POST /api/workspaces/{workspace_id}/messages
POST /api/workspaces/{workspace_id}/messages/upload
```

事件：

```text
GET /api/workspaces/{workspace_id}/events
GET /api/workspaces/{workspace_id}/events?after=evt_001
```

artifacts：

```text
GET /api/workspaces/{workspace_id}/artifacts
GET /api/workspaces/{workspace_id}/artifacts/content?path=paper/main.tex
GET /api/workspaces/{workspace_id}/artifacts/download?path=paper/main.pdf
```

checkpoint：

```text
GET  /api/workspaces/{workspace_id}/checkpoints
POST /api/workspaces/{workspace_id}/checkpoints/{checkpoint_id}/decide
```

## 6. 工作流与 HIL 设计

现有 workflow 支持 `auto_approve` 和 checkpoint，但 GUI 需要更自然的用户决策模型。

审批动作：

```text
confirm
edit
regenerate
ask
skip
abort
```

含义：

- `confirm`：接受 agent 建议，继续。
- `edit`：用户提供修改意见，agent 更新当前 plan 或 artifact。
- `regenerate`：要求 agent 重新生成当前方案。
- `ask`：用户提问，agent 解释后继续等待。
- `skip`：跳过非必需步骤。
- `abort`：终止当前任务。

关键 checkpoint：

- 题目理解完成后。
- 数据可行性分析后。
- 实施方案 plan 生成后。
- 模型路线确认前。
- 最终论文生成后。
- final gate 失败后。

新增 artifacts：

```text
discussion/implementation_plan_draft.json
discussion/implementation_plan_approved.json
discussion/user_decisions.jsonl
```

实施方案 plan 应包含：

- 题目理解摘要。
- 子问题拆解。
- 数据需求和数据可行性。
- RAG 范文/方法参考。
- 建模路线。
- 预期代码/求解任务。
- 预期图表。
- 论文结构。
- 风险点。
- 等待用户确认的问题。

## 7. 修改闭环设计

用户审核后可以通过 chat 提出自然语言修改意见。系统需要将意见路由到合适 stage。

新增 revision router：

```text
src/mcm_agent/agents/revision_router.py
```

输入：

- 用户消息。
- 当前 workspace 状态。
- 最近 final gate/reviewer/type-setting/validation 报告。
- 相关 artifacts 摘要。

输出：

```json
{
  "intent": "revise_model",
  "target_stage": "modeling_council",
  "affected_artifacts": [
    "reports/model_decision.md",
    "paper/sections/model.tex"
  ],
  "instruction": "Add sensitivity analysis for problem 3.",
  "requires_user_confirmation": true
}
```

第一版支持的 intent：

- `revise_plan`
- `revise_model`
- `revise_code`
- `revise_figure`
- `revise_paper_text`
- `revise_references`
- `revise_formatting`
- `explain_artifact`
- `unknown`

对于修改类 intent，GUI 先展示“agent 准备从哪个 stage 重跑”，用户确认后调用 `resume_mvp_workflow`。

## 8. 多模态输入设计

第一版多模态不做复杂视觉推理，只保证文件进入 workspace 并被记录。

图片来源：

- 题目上传区。
- chat 消息附件。

目标目录：

```text
input/images/
input/chat_uploads/
parsed/images/
reports/image_understanding.md
```

第一版行为：

- 保存图片。
- 在 message log 或 input manifest 记录图片路径。
- 如果配置了视觉 LLM 或 OCR provider，生成图片描述。
- 如果未配置视觉能力，报告“图片已保存但未解析”，不阻断主流程。

后续可扩展：

- OpenAI-compatible vision。
- OCR provider。
- 图表截图理解。
- 手写批注理解。

## 9. 前端实现建议

推荐前端栈：

```text
Vite + React + TypeScript
```

原因：

- 本地工具型产品足够轻。
- 与 FastAPI 后端解耦。
- 开发速度快。
- 后续可静态打包给 FastAPI 托管。

页面结构：

```text
frontend/
  src/
    api/
    components/
    pages/
      SettingsPage.tsx
      KnowledgeBasePage.tsx
      WorkspaceListPage.tsx
      WorkspacePage.tsx
    stores/
    types/
```

Workspace 页面布局：

```text
左侧：workspace 列表、stage 列表、文件树
中间：chat 和 plan/checkpoint 面板
右侧：agent activity、artifact preview、运行控制
```

第一版 UI 目标是清晰稳定，不做复杂动画和装饰。

## 10. 分阶段实施路线

### K：GUI Service Foundation

目标：

- 增加 FastAPI 服务层。
- 增加 config API。
- 增加 workspace API。
- 增加 progress event artifact。
- 支持从 API 启动 demo workflow 和真实 workflow。

验收标准：

- `mcm-agent gui` 能启动后端。
- API 能读取/保存配置。
- API 能创建 workspace。
- API 能上传题目和附件。
- API 能启动 run-demo。
- API 能读取 status 和 events。
- 不需要前端即可用 curl 或测试完成端到端验证。

### L：GUI MVP Frontend

目标：

- 增加基础 Web GUI。
- 设置页可编辑配置。
- workspace 页可上传文件、启动运行、查看进度。
- artifact preview 可查看主要报告和论文文件。

验收标准：

- 用户不用 CLI 即可完成 demo workflow。
- 用户能看到 stage 进度和最近事件。
- 用户能查看 `paper/main.tex`、`paper/main.pdf`、review reports。

### M：Structured RAG Case Library

目标：

- 实现 case schema。
- 支持 zip 上传。
- 支持 metadata 校验。
- 支持 case ingest。
- GUI 显示 case 状态和 chunk 数。

验收标准：

- 上传一个符合结构的范文 case 后，系统可 ingest。
- 不完整 case 会显示明确缺失项。
- workflow 的 methodology RAG 能使用这些 case。

### N：Interactive Planning And HIL

目标：

- 增加实施方案 plan checkpoint。
- 支持 confirm、edit、regenerate、ask、skip、abort。
- 用户在 GUI 中审核 plan 后再进入正式执行。

验收标准：

- 点击“开始思考”后，agent 生成 plan 并等待用户确认。
- 用户 edit 后，agent 更新 plan。
- 用户 confirm 后，workflow 继续。

### O：Chat Revision Loop

目标：

- 增加 revision router。
- 用户自然语言反馈可映射到修复 stage。
- GUI 显示即将重跑的 stage 和受影响 artifacts。

验收标准：

- 用户说“摘要重写得更自然”，系统路由到 paper writer。
- 用户说“图 2 换成折线图”，系统路由到 figure planning/visualization。
- 用户说“第三问模型太简单”，系统路由到 modeling/solver 相关 stage。

### P：Multimodal Task Inputs

目标：

- 支持图片和截图上传。
- 保存并记录图片路径。
- 有视觉 provider 时生成图片描述。

验收标准：

- 用户可在题目上传和 chat 中上传图片。
- 图片进入 workspace。
- 未配置视觉 provider 时不阻断流程。

### Q：Artifact Preview And Final Export

目标：

- 增强 PDF/LaTeX/figures/reports 预览。
- 支持下载 final package。
- 支持用户标注 artifact 问题并发起修改。

验收标准：

- 用户能在浏览器中审核最终论文。
- 用户能下载 `submission_package.zip`。
- 用户能对某个 artifact 直接发起修改反馈。

## 11. 不在第一阶段做的事情

以下内容明确不进入 K/L 第一版：

- 多用户账号系统。
- 云端部署和计费。
- 权限隔离和团队协作。
- 完整 SaaS 数据库。
- 复杂 WebSocket 协同编辑。
- 从零替换现有 CLI workflow。
- 全量 Typst 模板生态。
- 深度视觉推理。

这些能力可以后续扩展，但不应阻塞 GUI MVP。

## 12. 风险与应对

### 风险 1：workflow 运行时间长，用户以为卡住

应对：

- 每个 stage 开始和结束都写 progress event。
- 长 stage 内部至少每 30 秒写 heartbeat 或细粒度状态。
- GUI 显示“最后事件时间”和运行时长。

### 风险 2：API key 安全

应对：

- key 只写入本地 ignored JSON。
- GUI 不明文回显完整 key。
- provider smoke 输出不包含 key。

### 风险 3：GUI 与 CLI 状态不一致

应对：

- GUI 不维护独立真相。
- workspace artifacts 是唯一事实来源。
- API 从 `task_state.json`、`stage_runs.jsonl`、`progress_events.jsonl`、review artifacts 派生状态。

### 风险 4：用户上传的知识库结构混乱

应对：

- 强制 case schema。
- GUI 做结构校验。
- 不完整 case 可保存但不 ingest，直到补齐。

### 风险 5：修改反馈导致重复跑全流程

应对：

- revision router 输出目标 stage。
- GUI 让用户确认重跑范围。
- 优先局部 resume，而不是总是从 intake 开始。

## 13. 成功标准

GUI 产品化达到第一阶段成功，需要满足：

1. 新用户可以不使用 CLI 完成 demo run。
2. 用户可以在 GUI 中配置 API 并运行 provider smoke。
3. 用户可以上传本次题目和多个附件。
4. 用户可以看到 agent 每个阶段在做什么。
5. 用户可以查看生成的主要 artifacts。
6. 用户可以在关键 plan checkpoint 给出修改意见。
7. 用户可以下载最终论文或 submission package。
8. 所有新增后端行为有自动化测试覆盖。

## 14. 推荐下一步

先实现 **K：GUI Service Foundation**。这一阶段只建立服务 API、workspace 上传、配置读写、progress events 和后台运行能力，不做完整前端。

原因：

- 它是后续 GUI 的接口地基。
- 可以用测试和 curl 独立验证。
- 不会破坏现有 CLI。
- 能最快解决“用户不知道 agent 是否还在运行”的核心问题。

K 完成后再实现 **L：GUI MVP Frontend**，让用户真正通过浏览器操作完整 demo workflow。
