<p align="center">
  <a href="README.md"><img alt="English" src="https://img.shields.io/badge/English-默认语言-111827?style=for-the-badge"></a>
  <a href="README.zh-CN.md"><img alt="简体中文" src="https://img.shields.io/badge/简体中文-当前语言-10b981?style=for-the-badge"></a>
</p>

<p align="center">
  <img src="docs/assets/mcm-icm-agent-hero.svg" alt="MCM-ICM Agent architecture diagram" width="100%">
</p>

<div align="center">

# MCM-ICM Agent

**面向 MCM / ICM 数学建模论文的可追踪多 Agent 工作流。**

MCM-ICM Agent 会把一个赛题文件包转化为可审计 workspace：题目解析、数据可行性报告、模型路线决策、求解结果、证据注册表、claim-aware LaTeX 章节、review gate、修复日志和最终提交包。

[Agent 系统](#agent-系统) · [工作流](#工作流) · [命令手册](#命令手册) · [配置](#配置) · [Artifacts](#workspace-artifacts) · [GUI API](#本地-gui-api)

![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)
![CLI](https://img.shields.io/badge/interface-CLI%20%2B%20local%20GUI%20API-0f766e)
![FastAPI](https://img.shields.io/badge/gui%20api-FastAPI-009688)
![Tests](https://img.shields.io/badge/tests-pytest-0ea5e9)
![Status](https://img.shields.io/badge/status-active%20research%20prototype-f59e0b)

</div>

---

## 核心定位

这个仓库不是通用聊天 Agent，而是一个分阶段的数学建模论文系统。每个 Agent 都读取注册过的 workspace artifacts，写入新的 artifacts，并且必须通过明确的质量 gate，后续 Agent 才能依赖它的输出。

核心设计可以概括为：

```text
赛题文件包 -> Agent 工作流 -> 有证据支撑的论文 -> Review/repair loop -> 提交包
```

当前实现是 CLI-first,并且已经附带一个**零构建本地 Web GUI**(由 `mcm-agent gui` 托管),背后是 Workflow Control API:可在浏览器里配置 provider、上传题目、运行/恢复/停止工作流、实时看进度、审批 checkpoint、浏览 artifacts。今天已经比较完整的是 workflow 和 artifact contract;GUI 是可用的本地单用户应用,还不是托管多用户服务。

---

## Agent 系统

项目由一组专门 Agent 构成。它们不是靠隐藏上下文协作，而是通过 workspace 中的文件协作：报告、JSON 注册表、来源日志、证据记录、图表注册表、LaTeX 文件和 gate 决策。

### Agent 职责

| Stage | Agent | 读取 | 写入 | 作用 |
|---|---|---|---|---|
| `intake` | Intake Agent | 题目文件、附件、用户想法、模板目录 | `input_manifest.json`、复制后的输入文件 | 建立 workspace 输入契约。 |
| `mineru_extraction` | Document Extraction Agent | 输入 manifest、MinerU provider | `parsed/problem.md`、`parsed/problem.json`、解析报告 | 把题目 PDF 和模板转成可读文本与 layout artifacts。 |
| `extraction_quality_gate` | Extraction QA Gate | 题目解析 artifacts | `review/extraction_gate.json` | 当解析不完整时阻止后续推理。 |
| `problem_understanding` | Problem Understanding Agent | 解析后的题目 | `reports/problem_understanding.md` | 提取任务、约束、指标、歧义和隐含假设。 |
| `data_feasibility_scout` | Data Feasibility Scout Agent | 题意理解、搜索 provider | `reports/data_feasibility_report.md`、decision JSON | 在锁定方案前判断关键数据是否公开、需要代理变量、私有或未知。 |
| `research_reframing` | Research Reframing Agent | 数据可行性决策 | `discussion/reframing_options.md`、JSON | 当直接数据不可得时重构研究路线。 |
| `user_discussion` | User Discussion Agent | 题意报告、数据可行性、用户想法 | `discussion/confirmed_direction.md`、`direction_lock.json` | 锁定研究方向，或把新数据需求送回 scout。 |
| `methodology_rag` | Methodology RAG Agent | 本地 `knowledge_base/`、supervisor skills、MinerU | `rag/methodology_hits.json`、方法报告 | 检索优秀论文套路、方法笔记和 review checklist。 |
| `modeling_council` | Modeling Council | 题意理解、direction lock、LLM | `reports/model_candidates.md` | 提出候选模型路线和混合策略。 |
| `model_judge` | Model Judge Agent | 模型候选、LLM | `reports/model_decision.md`、`reports/experiment_spec.json` | 选择模型路线和实验契约。 |
| `modeling_quality_gate` | Modeling Plan Quality Agent | 实验 spec、模型决策 | `review/modeling_gate.json` | 拒绝薄弱、缺证据或定义不足的建模方案。 |
| `search_data` | Search & Data Agent | 搜索、抽取、官方数据 providers | `data/source_registry.json`、`data/retrieval_log.jsonl`、lineage 和 repair 文件 | 收集并注册来源、网页抽取和官方数据。 |
| `source_verifier` | Source Verifier Gate | 来源注册表 | `review/source_gate.json` | 判断来源是否足以支撑论文 claims。 |
| `data_eda` | Data / EDA Agent | 已注册数据和附件 | `reports/data_profile.md`、`data/processed/` | 剖析字段、清洗表格并记录限制。 |
| `solver_coder` | Solver / Coding Agent | 实验 spec、处理后数据 | `code/`、`results/model_route_summary.json`、`results/evidence_registry.json` | 运行确定性 solver modules 并注册数值证据。 |
| `validation_gate` | Validation Agent | 求解结果和证据 | `reports/validation_report.md`、`review/validation_gate.json` | 检查指标、鲁棒性、敏感性和证据覆盖。 |
| `figure_planning` | Figure Planning Agent | 结果、证据、来源注册表 | `figures/figure_plan.json` | 按目的、数据来源和目标章节规划图表。 |
| `visualization` | Visualization Agent | 图表计划和数据 | `figures/figure_registry.json`、SVG/PNG/PDF 输出 | 生成 vector-first 图和基于 artifacts 的概念图。 |
| `figure_quality_gate` | Figure Quality Agent | 图表注册表和图像输出 | `review/figure_gate.json`、质量报告 | 检查可读性、vector 输出、caption 和章节位置。 |
| `claim_planning` | Claim Planning Agent | 题意、模型决策、验证、RAG、证据、图表、来源 | `paper/claim_plan.json`、claim-plan 报告 | 写作前规划论文论证链。 |
| `paper_writer` | Paper Writer Agent | claim plan、证据、图表、来源、LLM | `paper/main.tex`、`paper/sections/` | 写带 trace comments 和引用的 LaTeX 章节。 |
| `paper_evidence_binding` | Paper Evidence Binding Agent | 论文章节、claim plan、registries | `review/paper_evidence_bindings.json`、报告 | 检查章节和 claim 是否有支撑。 |
| `typesetting` | Compliance、Reference、LaTeX、Repair Agents | 论文文件、引用、人类化、LaTeX provider | `paper/references.bib`、`review/typesetting_quality.json`、修复报告、可选 `paper/main.pdf` | 处理引用、原创性/人类化、编译、QA 和保守源码修复。 |
| `pre_submission_review` | Reviewer Agent | 主要 workspace artifacts | `review/reviewer_report.md`、`review/final_gate.json` | 做最终论文质量、证据和合规 review。 |
| `final_gatekeeper` | Final Gatekeeper | final gate 决策 | `review/final_gate.json` | 把 blocking findings 路由到责任修复阶段。 |
| `submission_packager` | Submission Packager | 已审核论文和 artifacts | `final_submission/submission_package.zip`、manifest、checklist 或 blocked report | 条件满足时生成最终提交包。 |

### 协作方式

Agent 由 graph-aware executor 协调：

1. 每个 stage 声明自己写出的 artifacts。
2. Gate stages 输出机器可读的 pass/fail 决策。
3. 失败 gate 会路由到责任阶段，例如 `search_data`、`modeling_council`、`solver_coder`、`figure_planning`、`paper_writer` 或 `typesetting`。
4. `mcm-agent inspect` 会解释当前 phase、最近失败 gate、repair stage 和最近运行历史。
5. `mcm-agent resume` 可以从指定 stage 或 `task_state.json` 里的 blocked repair point 继续。

更完整的拓扑图和说明见 [docs/AGENT_TOPOLOGY.md](docs/AGENT_TOPOLOGY.md)。

---

## 工作流

典型通过路径：

```text
intake
mineru_extraction
extraction_quality_gate
problem_understanding
data_feasibility_scout
user_discussion
methodology_rag
modeling_council
model_judge
modeling_quality_gate
search_data
source_verifier
data_eda
solver_coder
validation_gate
figure_planning
visualization
figure_quality_gate
claim_planning
paper_writer
paper_evidence_binding
typesetting
pre_submission_review
final_gatekeeper
submission_packager
```

关键循环：

| 循环 | 目的 |
|---|---|
| `data_feasibility_scout -> research_reframing -> user_discussion` | 避免锁定依赖私有、不可得或薄弱数据的方案。 |
| `user_discussion -> data_feasibility_scout` | 用户提出新的数据相关想法时重新检查可行性。 |
| `modeling_quality_gate -> modeling_council` | 在进入求解前修复薄弱模型路线。 |
| `validation_gate -> solver_coder/search_data/modeling_council` | 根据根因把失败送回代码、数据或模型修复。 |
| `figure_quality_gate -> figure_planning` | 在 claim plan 依赖图表前修复图表。 |
| `final_gatekeeper -> responsible stage` | 把最终 blocker 送到最小责任修复点。 |

操作细节、workspace 结构、gate 格式和常见失败模式见 [docs/WORKFLOW.md](docs/WORKFLOW.md)。

---

## 命令手册

先安装：

```bash
python -m pip install -e ".[dev]"
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

### `mcm-agent version`

打印当前 CLI 版本。

```bash
mcm-agent version
```

用于确认 shell 调用的是当前 editable checkout。

### `mcm-agent init-workspace`

初始化空 workspace。

```bash
mcm-agent init-workspace /tmp/mcm_agent_task
```

会创建基础目录和 `task_state.json`。适合在跑完整流程前了解 workspace 格式。

### `mcm-agent run-demo`

使用 fake providers 和内置样例输入运行确定性 demo。

```bash
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
```

这是安装后的首选 smoke test，不会消耗付费 API。

等价 helper：

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
```

### `mcm-agent run`

对真实赛题输入运行工作流。

```bash
mcm-agent run /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --attachment /path/to/extra.xlsx \
  --user-idea-file /path/to/user_idea.md \
  --template-dir /path/to/template_dir \
  --supervisor-skills-dir /path/to/skills \
  --auto-approve
```

参数：

| Option | 含义 |
|---|---|
| `WORKSPACE` | 写入所有输入、报告、artifacts 和最终包的目录。 |
| `--problem-file`, `-p` | 必需，赛题文件。 |
| `--attachment`, `-a` | 可重复，CSV、XLSX、图片、PDF 或其他赛题附件。 |
| `--user-idea-file` | 可选，用户初始想法、约束或建模偏好。 |
| `--template-dir` | 可选，比赛模板或格式样例目录。 |
| `--supervisor-skills-dir` | 可选，方法论/review skill notes，供 RAG 阶段读取。 |
| `--env-file` | 可选，旧版 `.env` 配置来源。 |
| `--config-file` | 推荐，本地 JSON 配置；这里的值覆盖 `.env`。 |
| `--auto-approve` | 自动批准 checkpoints；不加则保留人工审核点。 |

### `mcm-agent inspect`

解释 workspace 当前状态。

```bash
mcm-agent inspect /tmp/mcm_agent_task
```

会显示 current phase、unresolved issues、失败 gate、repair stage、模型路线、submission manifest 状态和最近 stages。运行像是卡住或被 gate 阻塞时，先看这个命令。

### `mcm-agent status`

打印简短 workspace 状态。

```bash
mcm-agent status /tmp/mcm_agent_task
```

比 `inspect` 更轻量：只看当前 phase、unresolved issue 数量和 pending checkpoints。

### `mcm-agent resume`

从指定 stage 或 `task_state.json` 中保存的修复点继续。

```bash
mcm-agent resume /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --from-stage validation_gate \
  --until-stage final_gatekeeper \
  --auto-approve
```

常见用法：

| 目标 | 示例 |
|---|---|
| 从 blocked repair stage 继续 | 省略 `--from-stage` |
| 重新跑数据收集之后的流程 | `--from-stage search_data` |
| 重新跑建模和求解 | `--from-stage modeling_council` |
| 只重跑论文写作 | `--from-stage claim_planning --until-stage final_gatekeeper` |
| 打包前停止 | `--until-stage final_gatekeeper` |

### `mcm-agent package`

为已审核 workspace 创建最终 zip。

```bash
mcm-agent package /tmp/mcm_agent_task
```

如果缺少 `paper/main.pdf` 或其他打包前提，会写入 `final_submission/submission_blocked.md` 并以非零状态退出。

### `mcm-agent provider-status`

显示当前会使用哪些 provider。

```bash
mcm-agent provider-status --config-file mcm_agent_config.local.json
```

修改配置后，用它确认 LLM、搜索、抽取、官方数据、MinerU 和 humanizer 选择。

### `mcm-agent provider-smoke`

测试真实 provider 通断，不打印密钥。

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

只测一部分：

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --providers llm,tavily,firecrawl,fred
```

包含 MinerU 解析：

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --mineru-file /path/to/sample.pdf
```

Smoke tests 可能调用付费或限流服务，所以是手动命令，不属于普通 pytest。

### `mcm-agent emit` 和 `mcm-agent approve-checkpoint`

底层 workflow 控制命令。

```bash
mcm-agent emit /tmp/mcm_agent_task user_review_requested
mcm-agent approve-checkpoint /tmp/mcm_agent_task checkpoint_001
```

适合实验 checkpoint 行为，或为未来 UI 做 coordinator 控件。

### `mcm-agent gui`

启动本地 Web GUI(静态前端 + Workflow Control API,基于 FastAPI)。

```bash
mcm-agent gui --host 127.0.0.1 --port 8787
```

在浏览器打开 `http://127.0.0.1:8787`。GUI 是零构建的(FastAPI 托管 HTML + Alpine.js + SSE,无 Node/构建步骤),有六个屏:设置、知识库、任务上传、讨论/规划、运行监控(实时阶段时间线 + 日志流 + checkpoint 审批)、产物浏览。它通过 Workflow Control API(run/resume/stop/approve/events/logs)驱动与 CLI 相同的工作流。

---

## 配置

推荐运行时配置是一个本地 JSON：

```bash
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

`mcm_agent_config.local.json` 被 git 忽略。仓库只提交 `mcm_agent_config.example.json`。

顶层 sections：

| Section | 用途 |
|---|---|
| `llm` | OpenAI-compatible API key、base URL、模型名和 timeout。 |
| `search` | Tavily、Firecrawl、Brave Search、Exa API keys。 |
| `official_data` | FRED、US Census、NOAA keys 和公共数据 base URLs。 |
| `mineru` | fake、本地 CLI 或 REST 文档解析模式。 |
| `humanizer` | UShallPass-compatible 人类化配置。 |
| `rag` | 本地知识库目录和 ingest extensions。 |
| `runtime` | 默认语言、重试、HTTP timeout、代码 timeout。 |

支持的 provider smoke IDs：

```text
llm, tavily, brave, exa, firecrawl, humanizer, mineru,
world_bank, oecd, undata, fred, us_census, noaa,
nasa_power, open_meteo, overpass
```

为了兼容旧用法，仍支持 `--env-file`。当 `.env` 与 JSON 同时提供时，JSON 优先。

---

## RAG 知识库

仓库只提交空目录：

```text
knowledge_base/
└── .gitkeep
```

`knowledge_base/` 下的用户文件会被 git 忽略。推荐结构：

```text
knowledge_base/
├── contest_rules/
│   └── mcm_rules.pdf
├── methods/
│   ├── topsis_notes.md
│   └── network_flow_examples.txt
└── papers/
    └── 2024_problem_c/
        ├── problem.pdf
        ├── data/
        └── excellent_paper.pdf
```

`methodology_rag` 阶段会直接分块 `.md` 和 `.txt`。`.pdf` 会在 MinerU 可用时解析。检索 chunk 写入 `rag/methodology_hits.json` 并带 provenance 字段。

RAG 材料用于指导建模和写作套路，不会自动成为已验证事实来源；事实 claims 仍需要注册 source 和 evidence。

---

## Workspace Artifacts

运行中生成的关键文件：

| Path | 作用 |
|---|---|
| `input/` | 复制后的题目、附件、模板和用户 notes。 |
| `parsed/problem.md` | 下游 Agent 使用的题目文本。 |
| `reports/problem_understanding.md` | 任务拆解和假设。 |
| `reports/data_feasibility_report.md` | 数据可得性和代理变量分析。 |
| `discussion/confirmed_direction.md` | 人/Agent 锁定的研究方向。 |
| `rag/methodology_hits.json` | 检索到的本地方法和论文写作指导。 |
| `reports/experiment_spec.json` | 模型路线、solver modules、输入、输出和指标。 |
| `data/source_registry.json` | 稳定来源记录，用于引用和证据。 |
| `data/retrieval_log.jsonl` | 搜索和抽取 trace。 |
| `results/model_route_summary.json` | 路线执行和 binding 状态。 |
| `results/evidence_registry.json` | 可用于论文的数值证据。 |
| `figures/figure_registry.json` | 图表元数据、source scripts 和目标章节。 |
| `paper/claim_plan.json` | claim-level 论证计划。 |
| `paper/main.tex` | 生成的 LaTeX 论文。 |
| `paper/references.bib` | 来源支撑的 bibliography。 |
| `review/*.json` | 机器可读 QA gates 和修复决策。 |
| `final_submission/` | 提交包、源码 zip、checklist、AI use report 或 blocked report。 |

---

## 本地 GUI API

启动服务：

```bash
mcm-agent gui --host 127.0.0.1 --port 8787
```

浏览器应用在 `/` 提供(静态资源在 `/static`)。它使用这些 endpoints:

| Endpoint | 用途 |
|---|---|
| `GET /` | GUI 外壳(`/static/*` 为资源)。 |
| `GET /api/health` | 健康检查。 |
| `GET /api/config` | 读取 masked runtime config。 |
| `POST /api/config` | 保存本地 runtime config(merge 式,不会覆盖已存密钥)。 |
| `POST /api/config/test-provider` | 通过 smoke 层测试某个 provider。 |
| `POST /api/workspaces` | 在 `.mcm_agent_workspaces` 下创建 workspace。 |
| `GET /api/workspaces` | 列出本地 workspaces。 |
| `POST /api/workspaces/{id}/files` | 上传 problem、attachment、template 或 chat 文件。 |
| `GET /api/workspaces/{id}/status` | 读取 task state、失败 gate 和近期 stages。 |
| `POST /api/workspaces/{id}/run` | 启动运行(后台线程;demo/auto_approve/from_stage/until_stage)。 |
| `POST /api/workspaces/{id}/resume` | 从某阶段或保存状态恢复。 |
| `POST /api/workspaces/{id}/stop` | 请求协作式停止。 |
| `GET /api/workspaces/{id}/run` | 运行状态:state、时长、待审 checkpoint、error。 |
| `POST /api/workspaces/{id}/checkpoints/{checkpoint_id}/approve` | 批准暂停的 checkpoint 并恢复。 |
| `GET /api/workspaces/{id}/events` | 阶段/日志/gate/checkpoint 的 SSE 事件流。 |
| `GET /api/workspaces/{id}/logs` | 近期阶段记录(SSE 回填/轮询)。 |
| `GET /api/workspaces/{id}/artifacts` | 列出生成 artifacts。 |
| `GET /api/workspaces/{id}/artifacts/content` | 读取文本 artifact。 |
| `GET /api/workspaces/{id}/artifacts/download` | 下载 artifact。 |
| `GET /api/knowledge/files` | 列出知识库文件及可索引性。 |
| `POST /api/knowledge/files` | 上传文件到 `knowledge_base/`。 |
| `DELETE /api/knowledge/files` | 删除知识库文件。 |
| `GET /api/knowledge/index-preview` | RAG 摄取离线预览(chunk 数)。 |

---

## 项目结构

```text
MCM-ICM-Agent/
├── mcm_agent_config.example.json
├── knowledge_base/
├── examples/demo_mcm_task/
├── scripts/
│   ├── run_demo_task.py
│   └── smoke_providers.py
├── src/mcm_agent/
│   ├── agents/
│   ├── core/
│   ├── providers/
│   ├── server/
│   ├── solver_modules/
│   ├── templates/
│   └── workflows/
├── tests/
└── docs/
```

重要文档：

| Document | 用途 |
|---|---|
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | 操作指南、stage 顺序、workspace 结构、gates 和失败恢复。 |
| [docs/AGENT_TOPOLOGY.md](docs/AGENT_TOPOLOGY.md) | Agent 图、职责和修复路由。 |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | 当前实现状态和剩余缺口。 |
| [docs/DESIGN.md](docs/DESIGN.md) | 长篇架构和产品设计。 |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | 历史与未来实现计划。 |

---

## 验证

README 和 server focused checks：

```bash
python -m pytest tests/test_docs.py tests/test_server_config.py tests/test_server_workspace.py -q
```

全量测试：

```bash
python -m pytest -q
```

Lint：

```bash
ruff check src tests scripts
```

---

## 成熟度

MCM-ICM Agent 是活跃研究原型。它有真实 workflow、真实 artifact contract 和大量测试，但不是自动获奖系统。

题意理解、模型有效性、数据假设、数值正确性、引用质量、论文风格、最终合规和正式提交决策，仍然需要人工审核。
