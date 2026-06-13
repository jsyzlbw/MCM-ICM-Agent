# MCM/ICM 数学建模 Agent 设计文档

## 1. 项目定位

本项目目标是设计一个面向 **美赛 MCM/ICM** 的数学建模 Agent 系统。用户上传赛题 PDF、附件数据、格式要求和可选 LaTeX 模板后，系统能够与用户讨论并确定论文思路，然后自动完成数据检索、建模、编码求解、图表生成、论文写作、排版、审查和修改，最终形成可提交的论文包。

系统默认采用 **关键检查点式人机协作**：

- 用户可以提供主要 idea，Agent 围绕用户思路完成建模和写作。
- 用户也可以只提供题目，Agent 基本全自动提出方案并推进。
- 关键节点需要向用户展示中间结论，允许用户确认、修改或要求重做。
- 如果中途存在无法解决的问题，系统可以用结构化占位符继续完成全文，最终统一告知用户待补充内容。

第一版优先服务 MCM/ICM 英文论文，默认排版引擎为 LaTeX。

## 2. 设计原则

### 2.1 证据链优先

论文中的每个关键数字、结论、图表和外部事实都必须能够追溯到明确来源：

- 竞赛附件数据
- 代码运行结果
- 联网搜索获取的外部数据
- RAG 检索到的论文或方法资料
- 用户明确提供的假设或 idea

Writer Agent 不允许凭空编造实验结果、数值结论或参考文献。

### 2.2 先思考，后写作

系统不能从题目直接跳到论文正文。必须先产出：

- 题意理解
- 子问题拆解
- 数据理解
- 候选模型
- 模型选择理由
- 实验计划
- 图表计划

只有这些中间产物通过检查后，才进入代码执行和论文写作阶段。

### 2.3 可自动，但不盲目自动

系统应支持高度自动化，但关键判断节点需要可解释、可审查、可回退。

默认检查点：

1. 题意理解和子问题拆解
2. 最终建模路线和论文框架
3. 初稿 PDF
4. 终稿提交包

### 2.4 合规润色，不做规避检测

用户提出的“降 AI 率 Agent”在本设计中定义为 **Compliance & Originality Agent**。它的目标是：

- 提升论文表达自然度
- 统一多 Agent 生成文本的风格
- 减少模板化、空泛、重复表达
- 检查引用、事实、数据来源和 AI 使用披露
- 给出需要人工补充或确认的段落

该模块不以规避 AI 检测、欺骗评审或伪装人工写作为目标。

## 3. 总体工作流

```text
用户上传赛题 PDF、附件、格式要求、模板、可选 idea
        ↓
Intake Agent 解析输入
        ↓
Document Extraction Agent 调用 MinerU 提取题面、公式、表格和图片
        ↓
Problem Understanding Agent 理解题意、拆解子问题
        ↓
User Discussion Agent 与用户讨论论文思路
        ↓
Modeling Council 生成多套建模方案
        ↓
Model Judge 敲定最终模型路线和论文框架
        ↓
Search & Data Agent 联网搜索外部数据
        ↓
RAG Agent 检索优秀论文、方法库和格式规范
        ↓
Data/EDA Agent 清洗数据、理解变量
        ↓
Solver/Coder Agent 编码求解
        ↓
Validation Agent 做结果验证、敏感性分析、鲁棒性分析
        ↓
Visualization Agent 生成论文级图表
        ↓
Paper Writer Agent 写论文正文
        ↓
LaTeX Typesetter Agent 排版、编译、修复格式
        ↓
Compliance & Originality Agent 合规润色和 AI 使用说明
        ↓
Reviewer Agent 模拟评委审查
        ↓
用户审查初稿并提出修改意见
        ↓
Revision Agent 循环修改直到终稿
```

## 3.1 Agent 协作机制

系统采用 **Coordinator + Artifact Blackboard + Event Queue** 的协作方式。各 Agent 不直接依赖彼此的私有上下文，而是通过标准化产物进行交接。

```text
Agent A
  ↓ 产出 artifact
Artifact Registry / Blackboard
  ↓ 触发 event
Coordinator Agent
  ↓ 分配任务
Agent B
```

这种设计有三个目的：

- 避免多 Agent 之间直接对话导致上下文混乱。
- 每一步都有可检查、可回放、可修改的文件产物。
- 用户修改某个阶段后，只需要从受影响节点继续运行，不必全流程重跑。

### 3.1.1 Artifact Registry

所有 Agent 的输入输出都登记到统一的 `artifact_registry.json`。

示例：

```json
{
  "artifact_id": "problem_understanding_v1",
  "type": "problem_understanding_report",
  "path": "reports/problem_understanding.md",
  "producer": "ProblemUnderstandingAgent",
  "depends_on": ["parsed_problem_pdf_v1", "attachment_inventory_v1"],
  "status": "approved",
  "created_at": "2026-06-12T20:00:00+08:00",
  "quality_checks": ["subproblem_count_checked", "format_requirements_checked"]
}
```

Artifact 状态：

- `draft`：刚生成，尚未检查。
- `review_required`：需要用户或 Reviewer Agent 审查。
- `approved`：可以作为下游输入。
- `rejected`：不可继续使用，需要重做。
- `superseded`：已有新版本替代。

### 3.1.2 Handoff Packet

每次 Agent 交接都必须生成一个 Handoff Packet，避免下游 Agent 猜测上游意图。

```json
{
  "from_agent": "ModelJudge",
  "to_agent": "SolverCoderAgent",
  "task": "implement_problem_1_model",
  "input_artifacts": [
    "reports/model_decision.md",
    "reports/experiment_plan.md",
    "data/processed/q1_dataset.csv"
  ],
  "expected_outputs": [
    "code/problem1.py",
    "results/problem1_results.csv",
    "results/problem1_metrics.json"
  ],
  "acceptance_criteria": [
    "code_runs_without_error",
    "metrics_saved_to_json",
    "all_key_values_registered_in_evidence_registry"
  ],
  "known_risks": [
    "external_data_has_missing_values_after_2022"
  ]
}
```

### 3.1.3 Event Queue

Coordinator Agent 通过事件驱动流程，而不是写死一条不可回退的流水线。

核心事件：

- `input.received`
- `document.parsed`
- `problem.understanding.ready`
- `user.direction.confirmed`
- `model.candidates.ready`
- `model.decision.approved`
- `data.ready`
- `code.completed`
- `validation.failed`
- `validation.passed`
- `figures.ready`
- `paper.draft.ready`
- `paper.compile.failed`
- `paper.review.failed`
- `paper.review.passed`
- `user.revision.requested`
- `submission.ready`

例如：

```text
Validation Agent 发现 Problem 2 结果不满足约束
        ↓
发布 validation.failed
        ↓
Coordinator 回滚到 Solver/Coder Agent
        ↓
Solver/Coder Agent 重新求解 Problem 2
        ↓
Validation Agent 只复查 Problem 2 和受影响章节
```

### 3.1.4 协作拓扑

```text
                           ┌────────────────────┐
                           │   Coordinator       │
                           └─────────┬──────────┘
                                     │
              ┌──────────────────────┴──────────────────────┐
              │                                             │
      ┌───────▼────────┐                          ┌─────────▼─────────┐
      │ Artifact        │                          │ Event Queue        │
      │ Registry        │                          │ / Task Scheduler   │
      └───────┬────────┘                          └─────────┬─────────┘
              │                                             │
  ┌───────────┼────────────┬──────────────┬─────────────────┼───────────┐
  │           │            │              │                 │           │
Intake   Modeling      Search/Data      Coder          Writer      Reviewer
MinerU   Council       RAG/EDA          Validation     Typesetter  Revision
```

### 3.1.5 用户协作点

用户不是每一步都被打断，而是在关键决策点参与：

1. `problem.understanding.ready`
   - 用户确认题意和子问题拆解。
2. `model.decision.ready`
   - 用户确认最终模型路线和论文框架。
3. `paper.draft.ready`
   - 用户审查初稿并提出修改意见。
4. `submission.ready`
   - 用户确认终稿提交包。

## 4. Agent 分工

### 4.1 Coordinator Agent

负责全局调度和状态管理。

职责：

- 创建任务工作区
- 维护任务状态
- 管理各 Agent 的输入输出
- 检查产物依赖关系
- 处理失败重试
- 记录未解决问题
- 决定何时进入用户检查点

关键产物：

- `task_state.json`
- `workflow_log.md`
- `unresolved_issues.md`
- `artifact_registry.json`
- `event_log.jsonl`

调度规则：

- 下游 Agent 只能读取 `approved` 或明确允许的 `draft` artifact。
- 如果某个 artifact 被用户修改，Coordinator 标记所有依赖它的下游 artifact 为 `stale`。
- 如果某个阶段失败，Coordinator 优先重跑最小受影响子图，而不是全流程重跑。
- 如果失败超过重试上限，生成占位符并进入 `unresolved_issues.md`。

### 4.2 Intake Agent

负责解析用户输入。

输入：

- 赛题 PDF
- 附件数据
- 格式要求文字
- LaTeX 模板
- 用户提供的主要 idea
- 用户上传的优秀论文或方法资料

职责：

- 提取题目文本
- 识别题目类型和比赛类型
- 解析提交格式要求
- 识别附件文件类型
- 判断是否需要联网补充数据
- 判断是否存在缺失信息

关键产物：

- `input_manifest.json`
- `format_requirements.md`
- `attachment_inventory.md`

### 4.3 Document Extraction Agent

负责调用 MinerU 对赛题、模板、参考论文和附件中的文档类文件进行结构化解析。

推荐工具：

- MinerU 本地 CLI
- MinerU REST API
- MinerU Docker / WebUI
- 后备解析器：PyMuPDF、pdfplumber、pandas、openpyxl

MinerU 适用原因：

- 支持 PDF、图片、DOCX、PPTX、XLSX。
- 可输出 Markdown 和 JSON，适合 RAG 与 Agent 下游处理。
- 支持公式转 LaTeX。
- 支持表格转 HTML。
- 支持扫描 PDF 和 OCR。
- 能按人类阅读顺序恢复多栏、复杂版面文本。
- 可提取图片、图片描述、表格标题和脚注。

输入：

- `input/problem.pdf`
- `input/attachments/`
- `input/template/`
- `input/reference_papers/`

输出：

- `parsed/problem.md`
- `parsed/problem.json`
- `parsed/problem_layout.json`
- `parsed/tables/`
- `parsed/images/`
- `parsed/formulas.json`
- `reports/extraction_quality_report.md`

处理流程：

```text
读取 input_manifest
        ↓
判断文件类型
        ↓
PDF/图片/DOCX/PPTX/XLSX → MinerU
        ↓
CSV/XLSX 原始数据 → pandas/openpyxl 辅助读取
        ↓
生成 Markdown/JSON/表格/图片
        ↓
Extraction QA Agent 检查解析质量
        ↓
通过后进入 Problem Understanding / RAG / Data Agent
```

质量检查：

- 是否提取到所有题目编号。
- 是否遗漏公式、表格或图片。
- 表格列名是否可读。
- PDF 页数与解析页数是否一致。
- 数学公式是否转换为可读 LaTeX。
- 如果解析质量低于阈值，切换 MinerU 高精度模式或请求用户确认。

### 4.4 Problem Understanding Agent

负责真正理解题目。

职责：

- 拆解背景、任务、约束和提交要求
- 识别子问题数量
- 对每个子问题说明输入、输出、目标、约束和评价指标
- 识别题目中的模糊表述和潜在歧义
- 列出容易忽略的隐含条件
- 给出初步建模方向

关键产物：

- `reports/problem_understanding.md`

该文件必须包含：

```markdown
# 题意理解报告

## 题目背景
## 子问题拆解
## 输入与输出
## 约束条件
## 评价指标
## 模糊表述与歧义
## 隐含条件
## 初步建模方向
## 需要用户确认的问题
```

### 4.5 User Discussion Agent

负责和用户讨论论文思路。

支持两种模式：

1. **用户主导模式**
   - 用户给出主要 idea
   - Agent 帮助完善模型、实验和论文结构

2. **AI 主导模式**
   - 用户只给出题目
   - Agent 自动提出 2-4 套方案
   - 用户选择或修改最终路线

职责：

- 用简洁语言向用户解释题意理解
- 提出可选建模路线
- 询问关键偏好
- 整理用户反馈
- 形成最终论文路线草案
- 将用户确认的取舍写入 `confirmed_direction.md`

关键产物：

- `discussion/user_brief.md`
- `discussion/confirmed_direction.md`

协作规则：

- 不直接把用户口头 idea 当成论文结论。
- 用户 idea 先进入 `user_brief.md`，再由 Modeling Council 转换成可检验模型。
- 如果用户 idea 与题目目标冲突，必须向用户解释冲突并给替代路线。

### 4.6 Modeling Council

负责生成多套候选模型。

它不是单一 Agent，而是一个模型方案委员会，至少包含以下角色：

- 简洁模型派：偏向可解释、稳健、易写论文
- 高精度模型派：偏向预测精度、复杂算法和机器学习
- 优化建模派：偏向目标函数、约束和最优策略
- 评委视角派：偏向论文可读性、合理性和可获奖性

职责：

- 为每个子问题提出候选模型
- 说明每个模型的适用条件
- 给出数学表达
- 分析数据需求
- 分析优缺点
- 预判实现难度和论文表达难度

关键产物：

- `reports/model_candidates.md`

协作方式：

```text
Problem Understanding Agent 输出题意报告
        ↓
Modeling Council 每个角色独立生成方案
        ↓
Council 汇总成候选池
        ↓
Model Judge 逐项打分
        ↓
用户确认最终路线
```

### 4.7 Model Judge

负责选择最终建模路线。

职责：

- 比较候选方案
- 检查模型是否与题目目标匹配
- 检查是否过度复杂
- 检查是否可用现有数据支撑
- 检查是否适合论文表达
- 生成最终模型路线

关键产物：

- `reports/model_decision.md`
- `reports/experiment_plan.md`

`model_decision.md` 必须说明：

- 最终采用的模型
- 放弃其他模型的原因
- 每个子问题的数学表达
- 目标函数和约束条件
- 需要运行的实验
- 需要生成的图表
- 敏感性分析方案

### 4.8 Search & Data Agent

负责联网搜索、外部数据获取、网页正文抽取和来源治理。第一版采用 **API 混合栈**，不把 MCP 作为核心依赖。

触发条件：

- 题目明确要求外部数据
- 附件数据不足
- 需要地区、人口、经济、天气、交通、地图、政策等真实数据
- 用户要求补充外部资料

默认 API 栈：

1. **Tavily**
   - 作为主搜索和研究型查询 provider。
   - 用于 web search、extract、crawl、map、research。
   - 适合 Agent 快速获得带摘要和相关性的网页候选。

2. **Firecrawl**
   - 作为网页正文抽取和 Markdown 化 provider。
   - 用于将复杂网页、报告页面、HTML 文档转成干净 Markdown。
   - 适合对 Tavily/Brave/Exa 返回的 URL 做深度抽取。

3. **官方数据 API**
   - World Bank、OECD、UNData、FRED、US Census。
   - NOAA、NASA、Open-Meteo 等天气和环境数据。
   - OpenStreetMap / Overpass 等地理和 POI 数据。
   - 这些来源优先级高于普通网页。

4. **学术 API**
   - OpenAlex、Semantic Scholar、Crossref、arXiv。
   - 用于论文、引用、方法背景和参考文献核查。

5. **Fallback provider**
   - Brave Search API：通用搜索 fallback，适合独立索引和稳定通用检索。
   - Exa：语义搜索、相似网页和研究型补充检索。

MCP 定位：

- MCP 可以作为开发期、本地 harness 或个人工具链适配层。
- 正式产品核心不依赖 MCP，因为 API 方式更利于密钥治理、缓存、审计、限流和可部署性。
- 若用户本地已有搜索 MCP，可以通过 Search Provider Adapter 接入，但输出仍必须进入统一的 `source_registry.json` 和 `retrieval_log.jsonl`。

数据策略：

- 优先使用官方机构、政府、国际组织、学术数据库和公开数据平台
- 所有外部数据必须记录来源 URL、访问时间、许可、引用建议
- 每条进入模型、图表或论文论证链的数据必须绑定 `source_id` 和 `datum_id`
- 不确定来源的数据只能作为背景参考，不能进入模型计算
- 所有下载或整理的数据进入 `data/`
- 每次搜索、抽取、筛选都写入 `data/retrieval_log.jsonl`
- 每条外部数据的来源链路写入 `data/data_lineage.json`
- 每个可引用来源的 BibTeX 候选写入 `data/citation_candidates.json`
- 所有可进入论文证据链的数据必须通过 Source Verifier 和 Data/EDA Agent 双重检查

关键产物：

- `data/source_registry.json`
- `data/data_lineage.json`
- `data/citation_candidates.json`
- `data/retrieval_log.jsonl`
- `data/external_data_notes.md`

内部子模块：

- `Query Planner`：把题目需求拆成具体查询，如数据集、背景事实、方法论文、政策约束。
- `Source Ranker`：根据权威性、时效性、可引用性、数据完整性排序。
- `Content Extractor`：调用 Firecrawl 或 provider 自带 extract 能力抽取正文。
- `Source Verifier`：检查来源是否可信、是否可引用、是否有许可或使用限制。
- `Data License Checker`：记录数据使用许可和引用方式。
- `Citation Builder`：为论文生成引用建议。

协作规则：

- Search & Data Agent 不能直接把网页内容交给 Writer Agent 写论文。
- 外部数据先进入 `source_registry.json` 和 `data/external/`。
- 外部数据被抽取为变量、指标、表格或模型输入时，必须进入 `data_lineage.json`。
- Writer Agent 和 Reference Manager 只能引用 `citation_candidates.json` 或人工确认过的来源。
- Data/EDA Agent 必须对外部数据做清洗和字段解释。
- Evidence Registry 只接受通过 Data/EDA Agent 或 Validation Agent 检查的数据，并保留 `lineage_ids`。
- 如果只有网页描述而无可下载数据，该来源只能用于背景说明，不能作为核心模型输入。

`source_registry.json` 示例：

```json
{
  "source_id": "worldbank_population_001",
  "title": "World Bank Population Data",
  "url": "https://...",
  "accessed_at": "2026-06-12",
  "license": "open data",
  "provider": "world_bank_api",
  "source_rank": "official",
  "used_for": "population feature construction",
  "citation": "World Bank, ..."
}
```

`retrieval_log.jsonl` 示例：

```json
{"time":"2026-06-12T20:30:00+08:00","provider":"tavily","query":"county level drought data United States 2023 csv","top_urls":["https://..."],"decision":"send_top_3_to_firecrawl"}
{"time":"2026-06-12T20:31:00+08:00","provider":"firecrawl","url":"https://...","output":"data/external/source_003.md","decision":"accepted_background_only"}
```

`data_lineage.json` 示例：

```json
{
  "datum_id": "datum_worldbank_population_001",
  "name": "population",
  "value": 331900000,
  "unit": "people",
  "entity": "United States",
  "time_period": "2023",
  "source_id": "worldbank_population_001",
  "source_url": "https://...",
  "source_title": "World Bank Population Data",
  "accessed_at": "2026-06-12T20:30:00+08:00",
  "local_path": "data/external/worldbank_population.csv",
  "extraction_method": "world_bank_api",
  "confidence": 0.95,
  "used_in": ["results/model_metrics.json", "figures/figure_001.pdf"]
}
```

### 4.9 RAG Agent

负责检索用户上传的优秀论文、建模方法、格式规范和科研方法论。它不替代模型推理，而是为 Modeling Council、Writer、Visualization 和 Reviewer 提供可追溯参考。

RAG 知识库分为六类：

1. `method_rag`
   - AHP
   - TOPSIS
   - 熵权法
   - ARIMA
   - LSTM
   - 回归
   - 聚类
   - 图论
   - 排队论
   - 整数规划
   - 遗传算法
   - 蒙特卡洛仿真

2. `paper_rag`
   - 优秀论文结构
   - 摘要写法
   - 章节组织
   - 图表风格
   - 敏感性分析写法

3. `competition_rag`
   - MCM/ICM 格式要求
   - AI 使用政策
   - 参考文献规范
   - 页数与提交要求

4. `code_rag`
   - 数据清洗代码模板
   - 优化模型代码模板
   - 预测模型代码模板
   - 可视化代码模板

5. `methodology_rag`
   - 接入 Supervisor-Skills 的 handbook 和 skills 方法论。
   - 吸收 idea evaluation、paper writing、figure design、pre-submission review 等规范。
   - 用于把“优秀科研直觉”转成可执行检查表。

6. `review_checklists`
   - 论文宏观逻辑检查
   - 写作细节检查
   - 英文语法和 AI tone 检查
   - LaTeX 格式检查
   - 图表质量检查

RAG 输出不得直接作为论文事实。它只能作为参考，正式结论仍需来自题目、数据、代码结果或明确引用。

Supervisor-Skills 接入方式：

- 不作为运行时硬依赖，不要求系统必须安装其 Skill。
- 将其 handbook、llms.txt、plugins/phd-research/skills 中的内容整理为可检索知识库。
- 检索结果必须转成当前数学建模任务的 checklist，而不是直接照搬科研论文写作模板。

重点吸收：

- `idea-evaluator`：用于模型路线是否有价值、是否过度复杂、是否匹配用户能力。
- `figure-designer`：用于 Figure Planning Agent 设计 motivated example、solution overview、experimental results figures。
- `pre-submission-reviewer`：用于 Reviewer Agent 做宏观逻辑、写作细节、英文、LaTeX、图表五维审查。
- 写作方法论：用于 Paper Writer Agent 组织 Introduction、Problem Analysis、Model Design 和 Results 叙事。

关键产物：

- `rag/retrieval_notes.md`
- `rag/methodology_hits.json`
- `review/methodology_checklist_report.md`

### 4.10 Data/EDA Agent

负责数据清洗和探索性分析。

职责：

- 读取附件和外部数据
- 统一字段名、单位和时间范围
- 检查缺失值、异常值、重复值
- 构造派生变量
- 生成统计摘要
- 判断数据是否足以支持模型

关键产物：

- `reports/data_profile.md`
- `data/processed/`
- `results/eda_summary.json`

协作规则：

- 只读取 Document Extraction Agent、Search & Data Agent 产出的结构化数据。
- 对 MinerU 提取出的表格必须二次校验列名、单位和行数。
- 清洗后的数据才允许进入 Solver/Coder Agent。
- 所有被论文引用的数据摘要必须进入 Evidence Registry。

### 4.11 Solver/Coder Agent

负责编码和求解。

职责：

- 根据 `experiment_plan.md` 编写代码
- 每个子问题单独实现
- 保存中间结果
- 保存最终结果
- 保存图表原始数据
- 自动处理代码报错
- 记录运行环境和依赖

关键产物：

- `code/problem1.py`
- `code/problem2.py`
- `code/problem3.py`
- `code/utils.py`
- `results/problem1_results.csv`
- `results/problem2_results.csv`
- `results/model_metrics.json`
- `results/run_log.md`

要求：

- 每个结果都要可复现
- 每张数据图都要有对应数据文件
- 不允许只在论文中写结果而不保存代码输出

### 4.12 Validation Agent

负责验证模型和结果。

检查内容：

- 结果是否满足约束
- 数值是否和代码输出一致
- 指标计算是否正确
- 是否有训练/验证划分
- 是否有误差分析
- 是否有敏感性分析
- 是否有鲁棒性分析
- 是否存在过拟合或过度解释

关键产物：

- `reports/validation_report.md`
- `results/sensitivity_analysis.csv`
- `results/robustness_checks.json`

### 4.13 Visualization Agent

负责图表规划、数据图生成、概念图生成和最终论文图表资产管理。第一版采用 **矢量优先** 策略。

图表生成分两步：

1. **Figure Planning**
   - 先根据 `model_decision.md`、`experiment_plan.md`、`validation_report.md` 和 `evidence_registry.json` 规划图表。
   - 输出 `figures/figure_plan.json`。
   - 明确每张图的目的、类型、数据来源、生成工具和使用章节。

2. **Vector-first Visualization**
   - 再根据 `figure_plan.json` 生成论文可用图表。
   - 最终论文图优先输出 PDF/SVG。
   - PNG 只作为预览或提交系统需要时的备用格式。

图表分三类：

1. **数据驱动图**
   - 必须由真实数据或模型结果生成
   - 例如折线图、热力图、箱线图、雷达图、地图、路径图、残差图、敏感性曲线
   - 默认工具：Python、matplotlib、seaborn、plotly、networkx
   - 地理类扩展工具：geopandas、cartopy、folium、OpenStreetMap/Overpass 数据
   - 必须保存生成脚本和图表源数据

2. **概念图**
   - 用于展示模型流程、算法框架、系统结构
   - 默认工具：Mermaid、Graphviz/DOT、TikZ、Draw.io
   - 最终输出优先 PDF/SVG
   - 复杂图可以先用 Mermaid/Draw.io 草稿，再用 TikZ 或矢量工具精修

3. **AI 风格草图**
   - infmind 等图像生成工具只用于视觉探索、灵感草稿或非正式预览
   - 不作为最终论文数据图
   - 若采用 AI 草图表达概念，必须由 Visualization Agent 转绘或重建为可编辑矢量图

规则：

- 数据图不能由纯图像生成 API 凭空生成
- 数据图必须能从 `code/` 和 `results/` 复现
- 图表优先输出为 PDF/SVG
- 图内不放大标题，标题交给 LaTeX caption
- 每张图要登记到 `figures/figure_registry.json`
- 每张图必须明确用于哪个论文段落或附录
- 不能为了“美观”改变数据含义、坐标比例或统计口径

关键产物：

- `figures/*.pdf`
- `figures/*.svg`
- `figures/*.png`
- `figures/figure_plan.json`
- `figures/figure_registry.json`

`figure_plan.json` 示例：

```json
{
  "figure_id": "fig_q1_prediction",
  "purpose": "show prediction performance for Problem 1",
  "figure_type": "data_plot",
  "source_data": ["results/problem1_predictions.csv"],
  "generation_script": "code/plot_problem1.py",
  "output_formats": ["pdf", "svg", "png"],
  "target_section": "paper/sections/results.tex",
  "caption_intent": "Prediction performance comparison for Problem 1."
}
```

`figure_registry.json` 示例：

```json
{
  "figure_id": "fig_framework",
  "type": "concept_diagram",
  "tool": "tikz",
  "source_file": "figures/source/fig_framework.tex",
  "outputs": ["figures/fig_framework.pdf", "figures/fig_framework.svg"],
  "used_in": ["paper/sections/model.tex"],
  "status": "approved"
}
```

### 4.14 Paper Writer Agent

负责论文写作。

写作策略：

每一节都基于：

```text
论点 + 证据 + 图表 + 解释 + 校验
```

Writer Agent 输入：

- `problem_understanding.md`
- `model_decision.md`
- `data_profile.md`
- `validation_report.md`
- `figure_registry.json`
- `evidence_registry.json`

输出：

- `paper/sections/abstract.tex`
- `paper/sections/introduction.tex`
- `paper/sections/assumptions.tex`
- `paper/sections/model.tex`
- `paper/sections/results.tex`
- `paper/sections/sensitivity.tex`
- `paper/sections/conclusion.tex`

要求：

- 不编造数据
- 不引用不存在的文献
- 不使用没有证据支撑的强结论
- 不出现内部路径名或 Agent 工作流痕迹
- 摘要必须包含每个子问题的方法和关键结果

### 4.15 LaTeX Typesetter Agent

负责论文排版。

职责：

- 选择或加载 LaTeX 模板
- 插入公式、图表、表格、参考文献
- 编译 PDF
- 修复编译错误
- 检查页数、图表位置、公式溢出
- 生成最终 PDF

关键产物：

- `paper/main.tex`
- `paper/references.bib`
- `paper/main.pdf`
- `paper/compile_log.txt`

### 4.16 Compliance & Originality Agent

负责合规、可读性、原创性检查和文本人性化润色。

职责：

- 统一全文风格
- 减少模板化表达
- 在保持学术性的同时，让语言更像真人写作
- 检查重复段落
- 检查引用完整性
- 检查 AI 使用披露
- 检查是否存在未解决占位符
- 标记需要用户人工确认的段落

推荐外部 Provider：

- UShallPass：用于段落级人性化改写，让文本在保持原意和学术表达的前提下更自然。

环境变量：

- `HUMANIZER_API_KEY`：UShallPass API key。
- `HUMANIZER_API_BASE_URL`：可选，默认 `https://leahloveswriting.xyz`。

UShallPass Provider Contract：

```json
{
  "provider": "ushallpass",
  "operation": "humanize_academic_text",
  "language": "en",
  "input_text": "...",
  "constraints": {
    "preserve_numbers": true,
    "preserve_citations": true,
    "preserve_equations": true,
    "preserve_technical_terms": true,
    "tone": "academic_natural"
  }
}
```

最小 API 约定：

- 英文改写：
  - `POST /api_v2/rewrite/english/jobs`
  - Body: `{"text": "..."}`
- 中文改写：
  - `POST /api_v2/rewrite/chinese/jobs`
  - Body: `{"text": "...", "mode": "light|aggressive|weipu|weipu_aggressive"}`
- 请求头：
  - `X-API-Key: $HUMANIZER_API_KEY`
  - `Accept: application/json`
  - `Content-Type: application/json`
- 轮询：
  - `GET <same-submit-path>/{task_id}`

轮询状态：

- `completed`：读取 `result`，进入 Fact Regression Check。
- `failed`：记录 `error.code` 和 `error.message`，该段落保留原文并标记人工处理。
- `timeout`：保留原文，写入 `humanization_diff.md` 和 `unresolved_issues.md`。

错误处理：

- `AUTH_ERROR`：提示用户检查 `HUMANIZER_API_KEY`，不静默重试。
- `RATE_LIMITED`：等待后重试，超过重试上限则跳过该段。
- `INVALID_PARAMETER`：检查文本是否为空或中文 mode 是否有效。
- `SERVICE_UNAVAILABLE`：记录服务不可用，保留原文。

默认模式：

- MCM/ICM 英文论文默认使用英文 endpoint。
- 中文论文默认 `light`。
- 中文 `aggressive`、`weipu_aggressive` 可能消耗更多额度，提交前需要用户确认。

处理流程：

```text
Paper Writer Agent 生成章节
        ↓
Fact Lock：锁定数字、公式、引用、图表编号、专业术语
        ↓
Compliance & Originality Agent 拆分可改写段落
        ↓
调用 UShallPass 或其他 humanization provider
        ↓
Fact Regression Check：检查数字、引用、公式是否被改坏
        ↓
Academic Tone Check：检查是否仍保持正式学术语气
        ↓
生成修改 diff 和 originality_report
        ↓
用户审查需要人工确认的段落
```

隐私提示：

- 提交到 UShallPass 的文本会发送到第三方服务器处理，并可能出现在用户账号历史中。
- 未公开论文、敏感数据、个人信息、商业机密或 NDA 内容默认不发送给外部 humanizer。
- 如果用户允许发送，系统应只发送待改写段落，不发送完整项目目录、原始数据和无关上下文。

禁止改写的内容：

- 数值结果
- 公式
- 变量符号
- 图表编号
- 参考文献编号
- 数据来源
- 模型名称
- 代码输出
- 评估指标名称

允许改写的内容：

- 句式节奏
- 段落衔接
- 过度模板化表达
- 重复措辞
- 不自然的连接词
- 太像机器生成的泛泛总结

后备外部 API：

- 可读性检查 API
- 语法检查 API
- 引用检查 API
- 重复率检查 API
- AIGC 风格风险提示 API

注意：该 Agent 不以欺骗评审、隐藏 AI 使用或规避比赛规则为目标。它的定位是学术润色、风格统一和合规审查。最终论文仍应按比赛要求披露 AI 辅助使用情况。

关键产物：

- `review/originality_report.md`
- `review/humanization_diff.md`
- `review/fact_regression_report.md`
- `final_submission/AI_use_report.md`

### 4.17 Reviewer Agent

负责模拟评委审稿。

评审维度：

- 是否切题
- 模型是否合理
- 假设是否可信
- 数据是否充分
- 代码结果是否支撑结论
- 图表是否清晰
- 敏感性分析是否充分
- 论文叙事是否连贯
- 是否符合 MCM/ICM 格式

输出：

- `review/reviewer_report.md`
- `review/methodology_checklist_report.md`

报告格式：

```markdown
# 自动评审报告

## 总体评分
## 主要优点
## 高风险问题
## 需要修改的问题
## 可能影响奖项的问题
## 修改建议
```

Supervisor-Skills 检查表映射：

- 宏观逻辑：检查论文是否有清晰的 problem → model → experiment → result → implication 链条。
- 写作细节：检查摘要、引言、模型假设、结果叙事是否有空泛段落。
- 英文表达：检查 AI tone、重复连接词和不自然表达。
- LaTeX 格式：检查公式、引用、图表、表格和页数。
- 图表质量：检查是否有 motivated example、solution overview、experimental results 三类核心图。

### 4.18 Revision Agent

负责根据用户和 Reviewer Agent 的意见修改论文。

职责：

- 解析用户批注
- 判断需要修改的章节
- 判断是否需要重新跑代码
- 更新论文文本
- 更新图表和结果引用
- 重新编译 PDF
- 生成修改摘要

关键产物：

- `review/revision_requests.md`
- `review/revision_summary.md`
- `paper/main_revised.pdf`

## 5. 用户交互设计

### 5.1 初始输入

用户可以上传：

- 赛题 PDF
- 附件数据
- 格式要求文本
- LaTeX 模板
- 主要 idea
- 参考论文
- 方法资料

### 5.2 第一次讨论

Agent 向用户展示：

- 题目理解
- 子问题拆解
- 可选建模路线
- 需要用户确认的问题

用户可以：

- 指定主要 idea
- 选择 AI 推荐路线
- 修改模型方向
- 要求更简单或更复杂
- 要求偏重可解释性、精度或论文美观

### 5.3 路线确认

Agent 输出：

- 最终论文主线
- 每个子问题的模型
- 实验计划
- 图表计划
- 预计论文结构

用户确认后，系统进入自动生成阶段。

### 5.4 初稿审查

Agent 生成完整论文后，用户审查 PDF 并给修改意见。

用户意见可以是：

- 修改某段文字
- 替换模型
- 添加图表
- 调整结论
- 改摘要
- 改排版
- 要求更像美赛高奖论文

Revision Agent 根据意见自动修改。

## 6. 占位符机制

如果系统无法解决某个问题，可以插入结构化占位符：

```text
[[UNRESOLVED:
reason = "缺少某城市 2023 年交通流量数据"
needed_input = "用户上传数据或允许联网搜索替代数据"
affected_section = "Problem 2 Results"
]]
```

规则：

- 占位符可以存在于初稿
- 占位符必须记录到 `unresolved_issues.md`
- 终稿提交前必须清除所有占位符
- Reviewer Agent 必须阻止含占位符的论文进入 `final_submission/`

## 7. 证据注册系统

系统维护 `results/evidence_registry.json`，记录论文中所有关键证据。

示例：

```json
{
  "evidence_id": "q1_rmse_001",
  "claim": "The model achieves RMSE = 2.31 on the validation set.",
  "value": 2.31,
  "source_type": "code_output",
  "source_path": "results/problem1_metrics.json",
  "generated_by": "code/problem1.py",
  "used_in": ["paper/sections/results.tex"]
}
```

Writer Agent 写论文时必须引用 evidence registry。

## 8. 运行时目录结构

每次比赛任务建议使用如下目录结构：

```text
workspace/
├── task_state.json
├── artifact_registry.json
├── event_log.jsonl
├── unresolved_issues.md
├── input/
│   ├── problem.pdf
│   ├── attachments/
│   ├── template/
│   └── user_idea.md
├── parsed/
│   ├── problem.md
│   ├── problem.json
│   ├── problem_layout.json
│   ├── tables/
│   ├── images/
│   └── formulas.json
├── discussion/
│   ├── user_brief.md
│   └── confirmed_direction.md
├── rag/
│   ├── retrieval_notes.md
│   ├── methodology_hits.json
│   └── review_checklists/
├── reports/
│   ├── extraction_quality_report.md
│   ├── problem_understanding.md
│   ├── data_profile.md
│   ├── model_candidates.md
│   ├── model_decision.md
│   ├── experiment_plan.md
│   └── validation_report.md
├── data/
│   ├── raw/
│   ├── external/
│   ├── processed/
│   ├── source_registry.json
│   ├── data_lineage.json
│   ├── citation_candidates.json
│   ├── retrieval_log.jsonl
│   └── external_data_notes.md
├── code/
│   ├── problem1.py
│   ├── problem2.py
│   ├── problem3.py
│   └── utils.py
├── results/
│   ├── problem1_results.csv
│   ├── problem2_results.csv
│   ├── model_metrics.json
│   ├── sensitivity_analysis.csv
│   ├── robustness_checks.json
│   └── evidence_registry.json
├── figures/
│   ├── figure_plan.json
│   ├── figure_registry.json
│   ├── source/
│   ├── fig_q1_prediction.pdf
│   ├── fig_q1_prediction.svg
│   ├── fig_q2_optimization.pdf
│   └── fig_framework.pdf
├── paper/
│   ├── main.tex
│   ├── references.bib
│   ├── sections/
│   ├── compile_log.txt
│   └── main.pdf
├── review/
│   ├── reviewer_report.md
│   ├── methodology_checklist_report.md
│   ├── originality_report.md
│   ├── humanization_diff.md
│   ├── fact_regression_report.md
│   ├── revision_requests.md
│   └── revision_summary.md
└── final_submission/
    ├── final_paper.pdf
    ├── AI_use_report.md
    ├── source_code.zip
    └── submission_package.zip
```

## 9. MVP 范围

第一版 MVP 不追求覆盖所有数学建模题，而是先打通完整闭环。

优先支持题型：

1. 预测类
2. 优化类
3. 多指标评价类

MVP 输入：

- 赛题 PDF
- 附件 CSV/XLSX
- 可选 LaTeX 模板
- 可选用户 idea

MVP 输出：

- 题意理解报告
- 模型选择报告
- 实验代码
- 结果表
- 图表
- LaTeX 论文
- PDF 初稿
- 自动评审报告
- AI 使用报告

MVP 检查点：

1. 题意理解确认
2. 模型路线确认
3. 初稿审查
4. 终稿确认

## 10. 参考项目启发

### 10.1 Agent Laboratory

Agent Laboratory 将科研任务拆成：

- Literature Review
- Experimentation
- Report Writing

可借鉴点：

- 将复杂科研任务拆成阶段
- 每个阶段都有明确产物
- 实验代码和论文写作分离
- 人类负责 idea 和判断，Agent 负责执行

### 10.2 AI Scientist

AI Scientist 的流程包括：

- idea generation
- novelty search
- experiment planning
- code execution
- figure generation
- paper writing
- automated review

可借鉴点：

- 自动提出 idea
- 自动跑实验
- 自动画图
- 自动写论文
- 自动评审并迭代

### 10.3 STORM

STORM 强调写作前的资料收集、视角扩展和大纲生成。

可借鉴点：

- 不直接写长文
- 先构建资料和观点
- 通过不同视角补充问题
- 大纲先行，再写正文

### 10.4 MathModelAgent

MathModelAgent 的启发：

- 数学建模任务可以拆成建模手、代码手、论文手
- Code Interpreter 对数模非常关键
- 工作流比完全开放式 Agent 更稳定
- Skill 化的阶段任务便于复用和扩展

## 11. 风险与应对

### 11.1 偏题风险

风险：Agent 可能误解题意。

应对：

- 强制生成题意理解报告
- 用户确认子问题拆解
- Reviewer Agent 检查是否切题

### 11.2 数据幻觉风险

风险：Agent 编造数据或引用。

应对：

- 外部数据必须进入 source registry
- 论文数字必须进入 evidence registry
- Writer Agent 不允许使用未注册证据

### 11.3 模型过度复杂

风险：复杂模型难解释、难验证。

应对：

- Modeling Council 必须包含简洁模型派
- Model Judge 比较复杂度和论文表达难度
- 优先选择可解释、可验证、可写清楚的模型

### 11.4 图表好看但无意义

风险：生成精美但没有数据支撑的图。

应对：

- 数据图必须由真实数据生成
- 概念图和数据图分离
- 每张图登记数据来源

### 11.5 论文风格模板化

风险：多 Agent 写作导致风格割裂或 AI 味明显。

应对：

- Compliance & Originality Agent 统一文风
- 删除空泛表达
- 用具体数据和图表支撑段落
- 保留用户 idea 和人工修改痕迹

### 11.6 格式或编译失败

风险：LaTeX 编译错误、图片缺失、引用错误。

应对：

- Typesetter Agent 自动编译
- 编译失败必须修复
- 终稿前检查页数、引用和图表

### 11.7 联网数据污染

风险：Search Agent 找到 SEO 垃圾网页、过期数据、不可引用数据或与题目口径不一致的数据。

应对：

- API 搜索结果必须经过 Source Ranker 和 Source Verifier。
- 外部数据必须进入 `source_registry.json`。
- 网页抽取日志必须进入 `retrieval_log.jsonl`。
- 官方数据 API 优先于普通网页。
- 无法确认来源和许可的数据不能进入模型计算。

### 11.8 AI 草图误用

风险：infmind 等工具生成的非矢量图被误用为正式论文图，或生成与真实数据不一致的图。

应对：

- AI 图片只作为概念草图或视觉参考。
- 最终论文图必须由代码、Mermaid、Graphviz、TikZ、Draw.io 或 SVG/PDF 工作流生成。
- 数据图必须可复现，且登记到 `figure_registry.json`。

## 12. 后续扩展

后续可以扩展：

- 支持 Typst
- 支持国赛中文论文
- 支持自动生成提交演示材料
- 支持多模型并行求解
- 支持视觉模型检查图表质量
- 支持更强的评委打分模拟
- 支持比赛时间管理和进度提醒
- 支持团队协作批注

## 13. 关键第三方工具选型

### 13.1 MinerU

定位：文档解析与多模态内容提取引擎。

在本系统中的职责：

- 解析赛题 PDF。
- 提取题面中的表格、公式、图片和题号结构。
- 将参考论文转换为 Markdown/JSON，供 RAG 入库。
- 将 LaTeX 模板说明、格式要求等文档转换为结构化文本。
- 对扫描版 PDF 开启 OCR。

优先使用方式：

1. 本地 CLI：适合用户本地部署和离线比赛环境。
2. REST API：适合云端服务和多用户系统。
3. Docker / WebUI：适合早期测试和人工校验。

集成要求：

- 所有 MinerU 输出必须保存到 `parsed/`。
- 原始文件不得被覆盖。
- 解析质量必须经过 `extraction_quality_report.md` 记录。
- 如果 MinerU 输出的表格进入建模数据，Data/EDA Agent 必须二次校验。

### 13.2 UShallPass

定位：文本人性化润色 Provider。

在本系统中的职责：

- 对 Paper Writer Agent 生成的英文段落进行自然化改写。
- 保持学术语气，减少机械、模板化和重复表达。
- 辅助生成更接近真人论文写作节奏的表达。

集成原则：

- 只处理可改写自然语言段落。
- 不处理数字、公式、引用、图表编号和技术术语。
- 改写后必须做 Fact Regression Check。
- 改写前后必须生成 diff，供用户审查。
- 英文论文默认调用 `/api_v2/rewrite/english/jobs`。
- 中文论文调用 `/api_v2/rewrite/chinese/jobs`，默认 `light` 模式。
- 使用 `HUMANIZER_API_KEY` 鉴权，可选 `HUMANIZER_API_BASE_URL`。
- 不承诺通过任何 AI 检测器，不以规避比赛规则为目标。

### 13.3 LaTeX

定位：MCM/ICM 论文排版主引擎。

在本系统中的职责：

- 组织论文源文件。
- 管理图表、公式、表格和参考文献。
- 编译最终 PDF。
- 支持用户上传官方或自定义模板。

### 13.4 Web Search / Data APIs

定位：外部数据和事实检索。

默认组合：

1. **Tavily**
   - 主搜索 provider。
   - 用于 search、extract、crawl、map、research。
   - 适合 Agent 研究型查询和快速候选源发现。

2. **Firecrawl**
   - 网页正文抽取 provider。
   - 用于将网页、报告和复杂 HTML 转成 Markdown 或结构化内容。
   - 常与 Tavily、Brave、Exa 返回的 URL 串联使用。

3. **官方数据 API**
   - World Bank、OECD、UNData、FRED、US Census。
   - NOAA、NASA、Open-Meteo。
   - OpenStreetMap / Overpass。

4. **学术 API**
   - OpenAlex、Semantic Scholar、Crossref、arXiv。

5. **Fallback**
   - Brave Search API：通用检索备用。
   - Exa：语义搜索、相似网页和补充研究检索。

所有联网数据必须进入 `source_registry.json`。
所有搜索和抽取操作必须进入 `retrieval_log.jsonl`。

### 13.5 Supervisor-Skills

定位：科研方法论和审稿检查表来源。

在本系统中的职责：

- 作为 `methodology_rag` 的主要来源之一。
- 为 Modeling Council 提供 idea evaluation 和 fatal flaw 检查。
- 为 Visualization Agent 提供科研图表设计规范。
- 为 Paper Writer Agent 提供论文结构和叙事方法。
- 为 Reviewer Agent 提供 pre-submission review 检查表。

集成原则：

- 第一版不直接安装和运行 Supervisor-Skills 的 Skill。
- 只把其 handbook 和 skills 内容入库为 RAG 与 checklist。
- 输出必须转化为数学建模语境，避免把顶会论文模板生硬套到 MCM/ICM。

### 13.6 infmind

定位：AI 视觉草图工具。

在本系统中的职责：

- 用于快速生成概念图风格参考。
- 用于探索模型流程图、系统框架图的视觉方向。
- 不作为最终论文数据图生成工具。

限制：

- infmind 输出不是矢量图，不适合作为最终论文主图。
- 若采用其结果，必须由 Visualization Agent 转绘为 Mermaid、TikZ、Draw.io、SVG 或 PDF。
- 不允许用 infmind 生成基于实验数据的结果图。

## 14. 第一版建设建议

建议按以下顺序实现：

1. 任务工作区和产物规范
2. MinerU 文档解析
3. Artifact Registry 与 Handoff Packet
4. 题意理解报告
5. 用户讨论与路线确认
6. 模型候选和模型选择
7. Supervisor-Skills 方法论 RAG 与检查表
8. 联网搜索 API 混合栈与外部数据登记
9. 代码执行与结果保存
10. Figure Planning 与矢量优先图表生成
11. LaTeX 论文生成
12. UShallPass 人性化润色适配器
13. 自动审稿与 methodology checklist
14. 用户反馈修改循环

第一版最重要的不是图表多精美，而是：

- 能稳定理解题意
- 能生成可执行模型计划
- 能跑出真实结果
- 能把结果写进论文
- 能生成可复现、可编辑、可审查的矢量图
- 能在不破坏事实的前提下优化文风
- 能被用户审查和修改
