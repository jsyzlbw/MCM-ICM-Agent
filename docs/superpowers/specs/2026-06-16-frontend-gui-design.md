# 前端 GUI MVP + 工作流控制 API 设计

状态日期:2026-06-16
状态:已与用户在 brainstorming 中确认四节设计,待用户复审本 spec。

## 1. 概述

把 CLI-first 的 MCM/ICM Agent 变成"敲一条命令 → 浏览器打开 → 在 GUI 里操作 agent 并实时看进度"的本地工具。本设计**不重写 agent 内核**:现有工作流、workspace artifacts、JSON 配置、RAG、provider、gate/review、LaTeX QA/repair、submission package 继续作为核心能力;GUI 通过服务 API 调用它们,并把运行过程转化为用户可见的阶段、事件、产物和审批动作。

本 spec 聚焦让产品**可操作、可观察**的最小完整闭环:补齐缺失的**工作流控制 API**(运行/恢复/停止/审批/事件)+ 一个**零构建前端**。

## 2. 与既有 spec 的关系(重要)

既有 `docs/superpowers/specs/2026-06-15-gui-productization-design.md` 是更宽的产品化设计。本 spec 是它 K/L 阶段的**具体落地设计**,并在两点上**有意覆盖**它:

- **前端技术栈**:既有 spec 建议 `Vite + React + TypeScript`;本 spec 改为 **零构建(FastAPI 托管静态 HTML + Alpine.js + SSE,无 node)**。理由见 §4.1。
- **事件模型**:既有 spec 建议新增 `progress_events.jsonl` + 轮询(后续升级 SSE);本 spec 直接用 **SSE 跟踪现有 `stage_runs.jsonl` / `task_state.json` + 运行线程的日志缓冲**,不新增 `progress_events.jsonl`。

**沿用**既有 spec 的部分:产品原则(本地优先、不隐藏过程、用户可干预、配置安全、复用内核、渐进交付)、6 个屏的职责划分、结构化知识库 case schema(§6.2)、以及 API 路径命名(`run/resume/stop/events/checkpoints/knowledge`)。

> 若用户更倾向 React 或轮询模型,以用户意见为准;本 spec 默认以 2026-06-16 brainstorming 的明确选择为准。

## 3. 已确认的决策

| 维度 | 决策 |
| --- | --- |
| 范围 | 后端工作流控制 API + 前端,一起做(否则 GUI 无法真正运行 agent) |
| 技术栈 | 零构建:FastAPI 静态托管 + Alpine.js + SSE,无 node/构建步骤 |
| 屏幕 | 6 个全做:设置、知识库、任务上传、讨论/规划、运行监控、产物浏览 |
| 视觉方向 | Friendly Workbench(紫色圆角、卡片、药丸状态、Agent 气泡),最接近本地 MathModelAgent 的紫色 shadcn 风格 |

## 4. 架构

### 4.1 前端形态(零构建)

- 一份 `index.html` 外壳 + Alpine.js 做视图切换(hash 路由 `#/settings` 等)+ 一份设计令牌 CSS。
- 前端库以**单文件 vendored**方式随包发布(Alpine ~15KB),不依赖 CDN、不依赖 node。
- 静态资源放 `src/mcm_agent/server/static/`,由现有 `mcm-agent gui` 的 FastAPI 用 `StaticFiles` 托管;`/` 返回 `index.html`。
- 前端仅通过 JSON API + 一条 SSE 取数据,不维护独立"真相",状态一律从后端/workspace 文件派生。

选择理由:目标 UX(命令→浏览器→交互)三种栈都满足,零构建用最少的活儿达成;项目本就是 Python + FastAPI,不引入第二套工具链;运行监控所需的交互(表单、上传、时间线、日志流、产物浏览)零构建完全胜任;后端 API 与前端解耦,**日后要换 React 不影响后端,不是死胡同**。

### 4.2 后端控制层

新增两个后端模块,尽量不动核心:

**运行注册表** `src/mcm_agent/server/run_registry.py`(进程内,线程式)
- 以 `workspace_id` 为键,保存:后台线程、状态(`running/paused/done/failed/stopped`)、起始时间、**停止标志**(`threading.Event`)、**日志环形缓冲**(deque)。
- 线程内调用现有 `run_mvp_workflow` / `resume_mvp_workflow`,**不重写工作流**。
- 每 workspace 同时只允许一个活动运行;重复启动返回 `409`。

**工作流路由** `src/mcm_agent/server/routes_workflow.py`
- `POST /api/workspaces/{id}/run`、`POST .../resume`、`POST .../stop`
- `POST .../checkpoints/{checkpoint_id}/approve`(可带 `user_message` 调整意见;复用 `Coordinator.approve_checkpoint`)
- `GET .../events`(SSE)、`GET .../logs`(轮询兜底/首屏回填)

### 4.3 执行器控制钩子(唯一的核心改动)

现状:`StageExecutor.run_until_complete` 一口气跑到底,阶段间不暂停;checkpoint 是 `Coordinator` 事后记录,执行器不会停下等人。要实现"暂停在某阶段等确认再继续",需给执行器加一个**阶段间控制钩子**:

- 给 `run_until_complete` 增加可选参数 `controller: Callable[[StageRunRecord], Literal["continue","pause","stop"]] | None`。
- 在每个阶段执行完、算出 `next_stage` 后调用 `controller`:
  - `stop` → 写状态后跳出循环(workspace 可后续 `resume`)。
  - `pause` → 写"待审批"标记后跳出循环;审批后由控制层用 `from_stage = next_stage` 触发内部 resume(新线程)。
  - `continue` → 照常继续。
- 该钩子只新增一个"阶段间询问"点,**不改动路由/gate 逻辑**。

控制层提供的 controller:停止标志置位 → `stop`;当前为**指定人审阶段**且非 `auto_approve` → `pause`;否则 `continue`。人审阶段集合(初版:`user_discussion`;可选扩展 `model_judge`、`paper_writer`)由配置给出。

### 4.4 执行模型:线程而非子进程

理由:实现简单;能直接用 FastAPI `TestClient` 覆盖测试;工作流本就文件驱动,崩溃可 `resume`;handoff 也建议先用后台线程注册表。代价:线程内硬崩溃会影响 server 进程——对本地单用户 MVP 可接受。API 与前端解耦,日后换子进程不影响前端契约。

### 4.5 SSE 事件流

- 执行器本就每阶段追加 `stage_runs.jsonl` 并更新 `task_state.json`。SSE 端点通过**按 offset 跟踪 `stage_runs.jsonl` + 监视 `task_state.json` + 读运行线程日志缓冲**产出事件。
- 不新增 `progress_events.jsonl`(与既有 spec 的差异):事件由现有文件 + 内存缓冲派生,既持久(刷新/重连可回放已完成运行)又低延迟(活动运行)。
- 首屏:`GET .../logs` + `.../status` 回填,再开 SSE;`EventSource` 自动重连。

### 4.6 密钥处理

`GET /api/config` 已脱敏(只返回 `*_configured` + 后 4 位)。设置页显示"已配置 ✓ ••••1234",可输入覆盖但不回显明文。运行日志/事件不含密钥(沿用 provider 不打印密钥的现有约定)。

## 5. 设计语言(Friendly Workbench)

设计令牌(写入 CSS 变量,便于全局换肤):

```
--bg #FAF9F6   --surface #FFFFFF   --surface-2 #F3F1EC   --border #ECECF0
--text #2A2A35 --muted #8A8A95
--violet #7C5CFF (主)  --violet-soft #EFEAFF
--teal #0EA5A4 (运行/成功)  --teal-soft #E7FAF2
--amber #F59E0B (待审/警告) --amber-soft #FEF3E2
--red #EF4444 (失败/停止)
--radius 14px  字体 Plus Jakarta Sans(随包或系统回退)  等宽 JetBrains Mono(日志)
```

组件约定:左侧固定导航 + 右侧内容;卡片 + 柔和阴影;状态用**药丸徽章**且**不只靠颜色**(图标+文字,无障碍);活动以"Agent 气泡"呈现,日志/代码用等宽。

## 6. 6 屏设计

### 6.1 设置(复用现有 config API)
按 config 分组渲染表单(`llm/search/official_data/mineru/humanizer/rag/runtime`)。每个 provider 一行带「测试连接」按钮(`POST /api/config/test-provider`,绿/红药丸)。保存 → `POST /api/config`。支持恢复默认(不清空已填 key,除非显式清空)。

### 6.2 知识库(需新增端点,采用既有 spec 的 case schema)
按 **case** 组织而非散装上传。沿用既有 spec 的目录与 `metadata.json` schema 及完整度校验(complete/incomplete/invalid),显示已 ingest 的 chunk 数、方法标签、来源文件,支持重新 ingest。新增 `routes_knowledge.py`:列 case / 上传(含 zip)/ 校验 / ingest 单个或全部 / 状态。这是 6 屏里(除控制 API 外)**唯一需要额外后端**的。

### 6.3 任务上传(复用 workspace + files API)
新建 workspace(`POST /api/workspaces`)→ 上传题目 PDF / 附件 / 模板 / 额外要求(`POST .../files`,按 `kind` 分类)→ 选项(模板 国赛/美赛、语言、自动批准 or 人工 checkpoint)→ 进入讨论或直接运行。后端把多输入映射为现有 `TaskInput`(初版以主问题文件为 `problem_file`,其余作为 attachments)。

### 6.4 讨论/规划(复用 artifact 读取 + 审批端点)
执行前展示题目理解、数据可行性、agent 提议方向(读 `reports/*`、`discussion/*`);用户讨论/编辑后确认方向。与监控页 checkpoint 卡同一机制,这里作为开跑前的独立规划视图。初版审批动作子集:**批准 / 调整(带意见)**;既有 spec 的完整 HIL 动作集(confirm/edit/regenerate/ask/skip/abort)为后续扩展。

### 6.5 运行监控(本设计核心,控制 API)
启动/恢复/停止;阶段时间线(含 gate 标记);活动流(Agent 气泡 + 等宽日志);运行计时 + 状态点;gate 失败原因与修复路线;暂停时**内联 checkpoint 审批卡**(批准/调整)。布局与配色见已确认的细化版 mockup。

### 6.6 产物浏览(复用现有 artifact API)
workspace 产物树(`GET .../artifacts`)、文本查看(`.../content`)、下载(`.../download`)、PDF/图/LaTeX 预览。Tab:概览 / 报告 / 图 / 论文 PDF / LaTeX / Review / 文件。

## 7. 数据流(一次运行生命周期)

1. 设置页写 provider → config 文件;上传页建 workspace + 传文件。
2. `POST .../run` → 控制层:读配置、构建 provider bundle、用已上传文件组 `TaskInput`,开后台线程跑 `run_mvp_workflow`(带控制钩子 + auto_approve 标志),立即返回运行句柄。
3. 线程逐阶段执行 → 每阶段追加 `stage_runs.jsonl`、更新 `task_state.json`、写产物、写日志缓冲。
4. 前端开 SSE → 实时更新时间线 + 活动流。
5. 到指定人审阶段且非 auto_approve,钩子返回 `pause` → 写待审标记、状态 `paused`、推 `checkpoint_pending`。
6. `POST .../checkpoints/{id}/approve`(可带调整)→ `approve_checkpoint` + 控制层用 `from_stage=next_stage` 触发内部 resume。
7. `POST .../stop` → 置停止标志 → 下个阶段边界优雅退出,状态 `stopped`,以后可 `resume`。
8. 完成 → 状态 `done`;submission 打包;产物可浏览/下载。

## 8. SSE 事件格式

`text/event-stream`,每条 `data:` 为一个 JSON:

```
status            {state, duration_s, current_stage}
stage_started     {stage_id, ts}
stage_completed   {stage_id, status, outputs[], next_stage, ts}
gate              {gate_id, status, failure_reason, repair_stage, ts}
log               {stage_id, level, message, ts}
checkpoint_pending{checkpoint_id, stage_id, title, proposed, ts}
run_finished      {state, ts}
```

支持 `?since=<offset>` 便于重连续传;无活动线程时仍可从文件回放历史。

## 9. 错误处理

- Provider 故障:测试连接逐项暴露;运行中阶段失败 → `stage_runs.jsonl` 记 `failed`+原因 → SSE 推失败 → 监控页标红;改配置后 `resume`。
- 重复 gate 失败 → `RepeatedGateFailureError` → `task_state` 写 `blocked_reason/blocked_repair_stage` → 监控页显示阻塞 + 修复路线,可从修复阶段恢复。
- 停止为**协作式**:当前阶段跑完才生效,UI 明示"将在当前阶段结束后停止"。
- 线程崩溃:注册表记 `failed` + 堆栈(脱敏),workspace 可恢复。
- SSE 断线:`EventSource` 自动重连,首屏回填后续传。
- 并发:每 workspace 一个活动运行,重复启动 `409`。
- 密钥绝不进日志/事件。

## 10. 测试

对齐现有 `tests/test_server_*.py`,用 `TestClient` + fake provider + 临时 workspace base:

- `tests/test_server_workflow_control.py`:fake run 跑完;状态流转;SSE 产出预期事件类型;`stop` → `stopped`;checkpoint 暂停 → 批准 → 续跑;双启动 `409`;从指定阶段 `resume`。
- 执行器控制钩子单测(continue/pause/stop,不走 HTTP)。
- `tests/test_server_knowledge.py`:case 列表/上传/校验/ingest(临时 `knowledge_base/`)。
- 静态托管冒烟测试(`/` 返回 index.html)。
- **诚实声明**:MVP 不含前端 JS 单测;UI 行为靠手动验证。

## 11. 文件级改动清单

新增:
```
src/mcm_agent/server/run_registry.py
src/mcm_agent/server/routes_workflow.py
src/mcm_agent/server/routes_knowledge.py
src/mcm_agent/server/static/index.html
src/mcm_agent/server/static/app.js
src/mcm_agent/server/static/styles.css
src/mcm_agent/server/static/vendor/alpine.min.js
tests/test_server_workflow_control.py
tests/test_server_knowledge.py
```

修改:
```
src/mcm_agent/core/stage_executor.py   # run_until_complete 增加 controller 钩子
src/mcm_agent/workflows/mvp.py         # 透传 controller + 日志 sink(线程可注入)
src/mcm_agent/server/app.py            # 挂 StaticFiles + 注册新路由
src/mcm_agent/cli.py                   # gui 命令:可选自动开浏览器
```

## 12. 范围之外 / 分阶段

不进入本 MVP:多用户账号、云部署/计费、权限、SaaS 数据库、WebSocket 协同、完整 HIL 动作集(edit/regenerate/ask/skip 的全部语义)、revision router 自然语言改稿路由、深度视觉推理。这些可在后续阶段(对应既有 spec 的 N/O/P/Q)扩展。

建议实现顺序:① 执行器控制钩子 + 运行注册表 + 控制/事件端点(纯后端,可测)→ ② 静态前端外壳 + 设置/上传/监控/产物四屏 → ③ 知识库(case schema 端点 + 屏)→ ④ 讨论/规划屏接入审批。

## 13. 风险与开放问题

- **人审阶段与 Coordinator checkpoint 的接线**:现有 mvp 处理器未普遍调用 `Coordinator.emit`,"待审 checkpoint"如何在指定阶段稳定产生需在实现期确定(指定阶段集合 + 在该阶段发起 pending checkpoint)。这是控制钩子落地的关键细节,留给实现计划。
- **pause 语义**:初版采用"暂停=退出线程,审批后内部 resume",复用现有 resume 机制、最稳;若需更"实时"的常驻线程阻塞(`threading.Event` 唤醒),作为可选优化。
- **长阶段心跳**:单个阶段可能很久,需阶段内定期写日志缓冲,避免 UI 看起来卡住(既有 spec 风险 1)。
- **TaskInput 多题目文件**:初版以主文件 + attachments 近似,正式多 problem files 模型后续再做。
- **前端依赖发布**:vendored Alpine 需纳入包数据(`pyproject` 的 package data / MANIFEST)。
