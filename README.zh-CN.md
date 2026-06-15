<p align="center">
  <a href="README.md"><img alt="English" src="https://img.shields.io/badge/English-默认语言-111827?style=for-the-badge"></a>
  <a href="README.zh-CN.md"><img alt="简体中文" src="https://img.shields.io/badge/简体中文-当前语言-10b981?style=for-the-badge"></a>
</p>

<p align="center">
  <img src="docs/assets/mcm-icm-agent-hero.svg" alt="MCM-ICM Agent animated workflow" width="100%">
</p>

<div align="center">

# MCM-ICM Agent

**面向 MCM / ICM 数学建模竞赛的可追踪多 Agent 研究与论文生成系统。**

上传赛题文件包，在一个本地 JSON 中配置模型和数据 API，用自己的优秀范文与方法笔记扩展 RAG 知识库，然后生成带证据、图表、引用、QA 报告和修复日志的 LaTeX/PDF 提交包。

[快速开始](#快速开始) · [工作流](#内部工作流) · [配置](#配置) · [RAG 知识库](#rag-知识库) · [本地 GUI API](#本地-gui-api) · [工作流文档](docs/WORKFLOW.md)

![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)
![CLI](https://img.shields.io/badge/interface-CLI%20%2B%20local%20GUI%20API-0f766e)
![FastAPI](https://img.shields.io/badge/gui%20api-FastAPI-009688)
![Tests](https://img.shields.io/badge/tests-pytest-0ea5e9)
![Status](https://img.shields.io/badge/status-active%20research%20prototype-f59e0b)

</div>

---

## 这个项目做什么

MCM-ICM Agent 按照真实数学建模比赛流程设计：

1. 配置 LLM、搜索、文档解析、学术写作、人类化和官方数据 API。
2. 把优秀论文、比赛规则、方法笔记放进本地 RAG 知识库。
3. 上传本次赛题、附件数据、格式模板和可选的用户思路。
4. Agent 解析题目、判断数据可得性，并提出建模方向。
5. 用户审核或批准检查点，Agent 继续完成建模、检索、求解、验证、写作和修复。
6. 用户检查生成的 workspace：证据、来源注册表、图表、claim plan、LaTeX、review 报告和最终提交包。
7. 如果某个 gate 失败，可以从对应阶段 resume，而不是从头重跑。

当前项目是 CLI-first 的参考实现，并带有本地 FastAPI GUI 后端基础。它还不是托管 SaaS，也没有提交完整生产前端。已经实现的核心能力是可追踪 Agent 工作流：每个重要决策都会写成 workspace artifact，方便检查、测试、恢复和人工审核。

---

## 功能概览

| 模块 | 当前已有能力 |
|---|---|
| 工作流运行时 | 图结构 stage executor，支持正常路径、修复路径、重复 gate 停止、checkpoint 和 resume。 |
| Workspace artifacts | 输入、解析文档、报告、数据 lineage、证据、图表、论文文件、review 输出和最终提交 manifest。 |
| 统一配置 | 一个被 git 忽略的本地 JSON：`mcm_agent_config.local.json`，统一配置模型、API、base URL、RAG 和运行参数。 |
| Provider smoke | CLI 和 GUI API 都能测试 LLM、Tavily、Brave、Exa、Firecrawl、MinerU、UShallPass 和官方数据 provider。 |
| RAG 知识库 | 空的用户填充目录 `knowledge_base/`，支持 `.md`、`.txt` 和 MinerU 解析后的 `.pdf`，并记录 provenance。 |
| 官方数据 API | World Bank、OECD、UNData、FRED、US Census、NOAA、NASA POWER、Open-Meteo、OSM/Overpass。 |
| 建模路线 | 用 recipe library 选择评价、优化、预测、仿真、分类、聚类、排队、网络、多目标决策等模型路线。 |
| 求解模块 | 确定性 baseline solver，写入 route summary、metrics、binding status 和 evidence registry。 |
| Claim-aware 写作 | `paper/claim_plan.json` 驱动摘要、引言、假设、模型、结果、敏感性、局限和结论。 |
| 引用系统 | 注册来源映射到 BibTeX key、citation candidates、references 和 paper evidence binding 报告。 |
| 图表 | 数据图和基于 artifacts 的概念图，输出 Mermaid source 与确定性 SVG。 |
| LaTeX QA | 类型排版 QA、保守的一轮源码修复、重新编译和修复报告。 |
| 打包 | 最终 zip、AI use report、checklist、machine-readable manifest；缺 PDF 或不满足条件时生成 blocked report。 |
| 本地 GUI API | 配置读取/保存、provider 测试、workspace 创建、文件上传、状态读取、artifact 列表/读取/下载。 |

---

## 快速开始

安装本项目：

```bash
git clone https://github.com/jsyzlbw/MCM-ICM-Agent.git
cd MCM-ICM-Agent
python -m pip install -e ".[dev]"
cp mcm_agent_config.example.json mcm_agent_config.local.json
mcm-agent version
```

运行内置确定性 demo：

```bash
mcm-agent run-demo /tmp/mcm_agent_demo --auto-approve
mcm-agent inspect /tmp/mcm_agent_demo
mcm-agent status /tmp/mcm_agent_demo
```

也可以用 helper script：

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
```

运行真实赛题：

```bash
mcm-agent run /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --attachment /path/to/extra.xlsx \
  --user-idea-file /path/to/user_idea.md \
  --auto-approve
```

多个附件就重复使用 `--attachment`。如果希望检查点等待人工审核，就不要加 `--auto-approve`。

从某个 stage 或修复点继续：

```bash
mcm-agent resume /tmp/mcm_agent_task \
  --config-file mcm_agent_config.local.json \
  --problem-file /path/to/problem.pdf \
  --attachment /path/to/data.csv \
  --from-stage validation_gate \
  --until-stage final_gatekeeper \
  --auto-approve
```

打包已审核 workspace：

```bash
mcm-agent package /tmp/mcm_agent_task
```

完整操作说明见 [docs/WORKFLOW.md](docs/WORKFLOW.md)。

---

## 配置

运行时配置集中在一个本地 JSON：

```bash
cp mcm_agent_config.example.json mcm_agent_config.local.json
```

把需要使用的 API 填入 `mcm_agent_config.local.json`。这个文件被 git 忽略，不会提交真实密钥。仓库只提交 `mcm_agent_config.example.json`。

顶层配置：

| Section | 用途 |
|---|---|
| `llm` | OpenAI-compatible API key、base URL、模型名、timeout。 |
| `search` | Tavily、Firecrawl、Brave Search、Exa API key。 |
| `official_data` | FRED、US Census、NOAA key，以及公共数据 provider 的 base URL。 |
| `mineru` | fake、本地 CLI 或 REST 文档解析模式。 |
| `humanizer` | UShallPass-compatible 人类化 provider。 |
| `rag` | 本地知识库目录和 ingest extensions。 |
| `runtime` | 默认语言、重试次数、HTTP timeout、代码执行 timeout。 |

查看当前 provider 选择：

```bash
mcm-agent provider-status --config-file mcm_agent_config.local.json
```

测试真实 API 通断，且不打印密钥：

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke
```

如果要测试 MinerU 真实解析，传一个小 PDF：

```bash
mcm-agent provider-smoke \
  --config-file mcm_agent_config.local.json \
  --workspace .smoke \
  --mineru-file /path/to/sample.pdf
```

为了兼容旧用法，仍然支持 `--env-file`。当 `--env-file` 和 `--config-file` 同时传入时，JSON 配置优先。

---

## RAG 知识库

仓库只提交一个空目录占位：

```text
knowledge_base/
└── .gitkeep
```

`knowledge_base/` 下的其他文件都会被 git 忽略。建议按结构放置材料，例如：

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

在 `methodology_rag` 阶段，`.md` 和 `.txt` 会直接分块；`.pdf` 会在 MinerU 可用时先解析再分块。检索结果写入 `rag/methodology_hits.json`，包含 `source_type`、`relative_path`、`chunk_id`、`page_hint` 和 `usage`。

本地 RAG 材料用于指导建模选择、论文结构、假设写法、局限性表达和 review checklist。它们不会自动变成已验证外部事实；事实性数据仍然需要进入 source registry 和 evidence flow。

---

## 内部工作流

正常路径如下：

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

系统的核心是 evidence-first：

| Artifact | 作用 |
|---|---|
| `data/source_registry.json` | 用稳定 ID 注册外部来源和元数据。 |
| `data/retrieval_log.jsonl` | 记录搜索与网页抽取动作。 |
| `data/data_lineage.json` | 记录外部数据事实与转换。 |
| `results/evidence_registry.json` | 记录模型输出和数值证据。 |
| `figures/figure_registry.json` | 记录图表元数据、source script 和论文目标位置。 |
| `paper/claim_plan.json` | 规划论文 claims、优先级、support IDs 和 unresolved reasons。 |
| `review/paper_evidence_bindings.json` | 检查 section-level 和 claim-level 支撑关系。 |
| `review/typesetting_quality.json` | LaTeX 和排版 QA 结果。 |
| `review/final_gate.json` | 最终 blocking findings 和修复路线。 |

如果 gate 失败，`mcm-agent inspect <workspace>` 会显示失败 gate、blocking findings 和 repair stage。用户补充数据、修改配置或调整输入后，用 `mcm-agent resume` 从修复阶段继续。

---

## 本地 GUI API

启动本地 GUI API 后端：

```bash
mcm-agent gui --host 127.0.0.1 --port 8787
```

常用 endpoints：

| Endpoint | 用途 |
|---|---|
| `GET /api/health` | 健康检查。 |
| `GET /api/config` | 读取已 mask 的运行时配置。 |
| `POST /api/config` | 保存本地运行时配置。 |
| `POST /api/config/test-provider` | 通过 smoke-test 层测试某个 provider。 |
| `POST /api/workspaces` | 在 `.mcm_agent_workspaces` 下创建 workspace。 |
| `GET /api/workspaces` | 列出本地 workspaces。 |
| `POST /api/workspaces/{workspace_id}/files` | 上传 problem、attachment、template 或 chat 文件。 |
| `GET /api/workspaces/{workspace_id}/status` | 读取 task state、失败 gate 和近期 stages。 |
| `GET /api/workspaces/{workspace_id}/artifacts` | 列出生成 artifacts。 |
| `GET /api/workspaces/{workspace_id}/artifacts/content` | 读取文本 artifact。 |
| `GET /api/workspaces/{workspace_id}/artifacts/download` | 下载 artifact 文件。 |

这部分是未来 GUI 的后端基础。当前仓库还没有生产级前端。

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

推荐继续阅读：

| 文档 | 用途 |
|---|---|
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | 操作命令、workspace 结构、stage、gate 和失败恢复。 |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | 当前实现状态和剩余缺口。 |
| [docs/DESIGN.md](docs/DESIGN.md) | 系统设计和长篇架构。 |
| [docs/AGENT_TOPOLOGY.md](docs/AGENT_TOPOLOGY.md) | Agent 角色和拓扑。 |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | 历史与后续实现计划。 |

---

## 验证

运行 focused checks：

```bash
python -m pytest tests/test_docs.py tests/test_server_config.py tests/test_server_workspace.py -q
```

运行全量测试：

```bash
python -m pytest -q
```

如果安装了 `ruff`：

```bash
ruff check src tests scripts
```

真实 provider smoke 可能调用付费或限流 API，因此需要手动运行，不放进普通 pytest。

---

## 当前成熟度

MCM-ICM Agent 是活跃研究原型。它已经能跑通可追踪工作流，生成大量数模论文 artifacts，并把中间状态暴露给用户审核。但它不能被当成“自动获奖系统”。

题意理解、模型有效性、数据假设、数值正确性、引用质量、论文风格、最终合规和正式提交决策，仍然需要人工判断。
