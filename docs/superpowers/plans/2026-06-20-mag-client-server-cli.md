# mag 客户端/服务端 CLI 重构计划（借鉴 KamaClaude 前端架构）

- 日期：2026-06-20
- 状态：设计+计划待复核（实现前）
- 决策（已与用户确认）：**完整客户端/服务端**——独立 core server(kernel) + NDJSON socket 线协议，CLI（以及将来 GUI）都是客户端。**做题工作流引擎保持我们现有结构不变**（StageExecutor / workflow_graph / gates / 领域 agents / MockJudge / LaTeX 全部不动），只把它的「输出 / 提问 / 进度 / 产物」改为**发事件**。
- 参考：KamaClaude（`WIRE_PROTOCOL.md`、`core/bus`、`core/events`、`core/loop`、client/server 分离）。我们借**前端架构与样式**，不借它的通用 agent-loop 内核。

---

## 1. 目标 / 非目标

### 目标
1. 把 mag 拆成两层：**core server（kernel）**承载逻辑（工作流/对话/命令/LLM/会话），**CLI client**只负责渲染事件 + 回传命令。
2. 二者通过 **NDJSON over TCP loopback** 的线协议通信（JSON-RPC 2.0 命令 client→server；事件信封 server→client），与 KamaClaude 同款。
3. 从**架构层面根除**当前 TUI 的耦合坑：流式写裸 stdout 画花、`console.input` 冻屏、ask 桥/`suppress_live_output` hack——这些在"kernel 永不碰终端、只发事件"的模型里**不可能发生**。
4. 为**将来 GUI**（用户远期目标）铺路：GUI 只是同一 socket 上的另一个客户端。

### 非目标
- 不改做题工作流/agent/gate 的**内部结构**（只在边界发事件）。
- 不做鉴权/多用户/远程（本地单机 loopback；端口仅绑 127.0.0.1）。
- 不把 mag 变成通用 agent-loop（明确不借 KamaClaude 的 `core/loop` 内核思路）。

---

## 2. 现状与痛点
- 单进程：`InteractiveSession.run_once` 直接 in-process 调 `workflow_adapter`/`cli_commands`/`chat`；全屏 `MagFullScreenApp` 也在同进程里调 `run_once`，靠 `ask 桥`/`suppress_live_output`/线程 executor 绕开终端冲突。
- 痛点：UI↔逻辑耦合（已连环踩坑：画花、冻屏、交互命令无法输入），且无法支撑多前端/GUI。
- 根因：逻辑层直接读写终端（`console.print` / `console.input`）。**正解 = 逻辑层只发事件，前端是唯一碰终端的人。**

---

## 3. 目标架构

```
┌──────────── CLI client (TUI) ────────────┐         NDJSON / TCP 127.0.0.1:<port>          ┌─────────── core server (kernel) ───────────┐
│  prompt_toolkit 全屏 App（已建，复用）      │  ── JSON-RPC 2.0 命令 (client→server) ──────▶ │  command router                             │
│  · 渲染事件流 → 对话区/状态行/spinner       │                                               │  EventBus + EventWriter(事件日志)            │
│  · 输入回车 → 发 input.submit               │  ◀── 事件信封 (server→client) ─────────────── │  Service: 持有 InteractiveSession/workflow   │
│  · ask/permission 事件 → 渲染并回传         │                                               │  做题工作流引擎（我们的，不变）              │
└────────────────────────────────────────── ┘                                               │  chat / commands / LLM provider             │
                                                                                             └─────────────────────────────────────────────┘
```

要点：**kernel 不 import rich.Console 去 print/input**；它只 `bus.emit(event)`。CLI 是唯一渲染者。`ask` 变成 `ask.request` 事件 + 等 `ask.answer` 命令；HITL 人审变成 `permission.request` + `permission.decide`。

---

## 4. 线协议（WIRE_PROTOCOL，仿 KamaClaude）

- **Transport**：TCP loopback `127.0.0.1:<port>`（env `MAG_HOST`/`MAG_PORT` 覆盖；默认按 workspace 路径哈希派生端口，避免多 workspace 冲突）。每条消息一行 `\n` 结尾 JSON（NDJSON）。
- **命令（client→server）**：JSON-RPC 2.0 请求，`params.type` 路由。
- **事件（server→client）**：`{"kind":"event","event":{"type":..., ...}}` 信封。
- **协议文档自动生成**：`scripts/gen_protocol_doc.py`（从 pydantic 模型导出，仿他的"Do not edit manually"）。

### 4.1 命令（初版）
| 命令 `type` | 参数 | 作用 |
|---|---|---|
| `core.ping` | `{client}` | 健康检查 → `pong` |
| `session.attach` | `{workspace}` | 建立/恢复会话，返回当前状态快照 |
| `input.submit` | `{text}` | 用户输入的一行（服务端按 `/` `!` `@` 普通文本路由——即把现有 `run_once` 分发搬到服务端） |
| `ask.answer` | `{ask_id, answer}` | 回应 `ask.request` |
| `permission.decide` | `{req_id, decision}` | 回应 `permission.request`（O7 人审 gate） |
| `interrupt` | `{}` | 中断进行中的 stage（Esc） |
| `exit` | `{}` | 客户端断开 |

### 4.2 事件（初版）
| 事件 `type` | 字段 | 渲染 |
|---|---|---|
| `step.started`/`step.finished` | `{step, stage_id, label}` | 状态行/进度（复用 `STAGE_LABELS`） |
| `assistant.chunk`/`assistant.text` | `{text}` | 对话区（流式逐块；markdown 收尾渲染） |
| `tool.call`/`tool.result` | `{name, input, exit_code, output}` | 对话区（shell `!` 等） |
| `output.text` | `{text, markdown}` | 对话区（命令正文/通知；`markdown=False` 保字面 `[ok]`） |
| `ask.request` | `{ask_id, prompt}` | 进入 ask 模式渲染 → 回传 `ask.answer` |
| `permission.request` | `{req_id, summary, detail}` | 审批 UI → 回传 `permission.decide`（O7） |
| `stage.progress` | `{label}` | spinner 文案 |
| `artifact` | `{kind, path}` | 提示产物（`paper/main.tex`、`output/draft/main.pdf`） |
| `error` | `{reason}` | 红色提示（沿用诚实报错） |
| `done` | `{}` | 一轮结束 |

---

## 5. 组件与文件

### server 端（新 `src/mcm_agent/server/`）
| 文件 | 职责 |
|---|---|
| `protocol.py` | 命令/事件的 pydantic 模型 + JSON-RPC 编解码 + 事件信封；单一真相，供文档生成 |
| `event_bus.py` | asyncio pub/sub；多客户端广播；统一现有 `event_log.jsonl` 为 `EventWriter`（持久化，供 trace 回放） |
| `router.py` | 命令 → handler；**复用现有 `run_once` 的分发逻辑**（`/`命令、`!`shell、`@`、普通文本），但 `ctx.printer`/`ctx.ask` 绑到事件 |
| `service.py` | 持有 `InteractiveSession`/`WorkspaceWorkflowAdapter`；驱动工作流；stage 进度→`step.*`；gate 人审→`permission.request` |
| `server.py` | asyncio TCP server；每连接一 client；命令分发 + 事件广播；按 workspace 单实例 |
| `app.py` | `mag serve` 入口 + 「无 server 则 spawn 子进程」逻辑 |

### core 改造（小，工作流结构不变）
- `cli_commands/base.py::CommandContext`：`printer(text)` → `bus.emit(output.text)`；`ask(prompt)` → `bus.emit(ask.request)` 并 `await` 对应 `ask.answer`（服务端用 asyncio `Future`/事件按 `ask_id` 配对）。
- `workflow_adapter`：`progress` 回调 → `step.*`/`stage.progress`；产物落盘后 → `artifact`；（O7）gate 需人审 → `permission.request` + 等 `permission.decide`。
- `chat`：流式 → `assistant.chunk`；非流式 → `assistant.text`。
- **降级 sink**：抽象一个 `EventSink` 接口；in-process/headless 模式用「直接打印 sink」（等价现有行为），socket 模式用「广播 sink」。这样 `run_once` 在非 TTY/测试下行为不变。

### client 端（复用现有 `src/mcm_agent/tui/`）
| 文件 | 职责 |
|---|---|
| `client.py`（新） | 连 socket；发 JSON-RPC 命令；异步读事件流；断线重连 |
| `fullscreen.py`（改） | 输入回车→`input.submit`；订阅事件→渲染；`ask.request`→ask 模式+回传；`permission.request`→审批 UI；`artifact`→产物提示。**删掉 ask 桥/suppress hack**（架构取代） |

---

## 6. 兼容与降级（关键：不破坏现有 553 测试）
- `mag`（无参，TTY）：若本地无该 workspace 的 server → spawn 子进程 server，再以 client 连上 → 全屏 App。
- `mag`（非 TTY / 管道 / CI / pytest）：**走 in-process headless**——直接 `run_once` + 「打印 sink」，**不起 socket**。现有 `run_once`/`CliRunner`/pexpect 行式测试**零改**（553 绿）。
- `mag serve`：显式起 server（供 GUI/调试/远端复用）。
- `mag --in-process`：强制单进程直跑（兜底/排障）。
- 任何 socket/server 故障 → 自动回退 in-process headless（永不卡死用户）。

---

## 7. 迁移策略
- `run_once` 保留为「逻辑分发」纯函数；它产出/提问改为通过注入的 `EventSink`（默认打印 sink=现有行为；socket 模式=广播 sink）。→ 现有测试用默认 sink，行为不变。
- 先做「事件化」（in-process sink），再上 socket。每阶段独立可用、可测、可同步 main。
- ask 桥/suppress_live_output 在 socket+事件落地后删除（它们是过渡 hack）。

---

## 8. 分阶段实施（每阶段 TDD、独立可用、同步 main）

> 注：以下为阶段级计划；**经你批准架构后**，再用 writing-plans 把每阶段拆成带 TDD 代码的可执行任务。

- **S1 协议与事件总线**：`protocol.py`（命令/事件模型 + JSON-RPC 编解码 + 信封）、`event_bus.py`、`EventWriter`（统一事件日志）。纯逻辑、可单测、无网络。
- **S2 核心 I/O 事件化**：`EventSink` 抽象；`CommandContext.printer/ask`、`chat` 流式、`workflow_adapter` 进度/产物 → 事件。默认「打印 sink」保持现有 `run_once` 行为等价（553 测试绿）。
- **S3 TCP server + client**：`server.py`（asyncio）、`router.py`（复用 run_once 分发）、`service.py`、`client.py`；JSON-RPC 收发、多客户端广播、按 workspace 单实例 + 自动 spawn。socket 冒烟测试。
- **S4 TUI 转事件客户端**：`fullscreen.py` 接 `client`，渲染事件、`ask.request`/`permission.request` 交互回传；**移除 ask 桥/suppress hack**。真 pty 验证（config 流程、聊天、`/start --lock --run` 出 PDF）。
- **S5 协议文档 + trace**：`scripts/gen_protocol_doc.py` 生成 `WIRE_PROTOCOL.md`；`mag trace` 回放事件日志（仿他）。
- **S6（铺路，可选）**：为未来 GUI 客户端定义最小接入示例（同 socket）。

---

## 9. 风险与缓解
| 风险 | 缓解 |
|---|---|
| 大重构、周期长 | S1-S2 即可拿到「事件解耦」收益（修掉耦合坑），S3-S4 再上 socket；每阶段独立同步 main，随时可停在一个可用态 |
| asyncio socket + 工作流同步重活 | 工作流在 executor/线程跑，事件经 loop 线程安全广播（`call_soon_threadsafe`） |
| 端口冲突/多 workspace | 按 workspace 路径派端口（或 unix domain socket）；单实例锁文件 |
| 测试复杂度上升 | **in-process headless 作为主测试面**（协议/路由/事件用单测；socket 仅薄冒烟）；保留 553 现有测试不动 |
| 本地单机上 client/server 略"重" | 用户已知并选择；收益是彻底解耦 + GUI 铺路；自动 spawn 让用户无感（仍是一句 `mag`） |

---

## 10. 复用 / 取代
- **复用**：现有全屏 App（completers/theme/welcome/keybindings）、工作流引擎、`run_once` 分发逻辑、事件日志。
- **取代/删除**：`ask 桥`、`suppress_live_output` hack（被「事件 + 客户端渲染」从架构上取代）。
- **明确不引入**：KamaClaude 的通用 agent-loop 内核（我们保留领域工作流）。

---

## 附：与 KamaClaude 的「借鉴映射」
| KamaClaude | mag 采用 |
|---|---|
| `WIRE_PROTOCOL`（NDJSON/TCP，JSON-RPC 命令 + 事件信封） | §4 同款线协议 |
| `core/bus` + `core/events`（EventBus + envelope + writer） | `server/event_bus.py` + `EventWriter` |
| client/server 分离（CLI 是瘦客户端） | §3 架构 |
| `permissions/`（审批） | `permission.request`/`decide`（落地 O7 人审 gate） |
| `trace` 命令（回放事件） | `mag trace` |
| `scripts/gen_protocol_doc.py` | 同名脚本自动生成协议文档 |
| **`core/loop`（通用 agent loop）** | **不采用**——保留我们的做题工作流引擎 |
