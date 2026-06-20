# 开发计划：交互式 /api（箭头选择+连通检查）与论文质量重写

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** (A) 让 `/api` 成为可上下选择、可查看/输入、能自动检查通断的交互面板；(B) 把论文从"artifact 字段拼接"重写为"LLM 按目标语言写出的可提交论述"，消除倒灌/混语/markdown 脏字符/流水账。

**Architecture:** 两个独立子系统，各自可单独发布。A 复用现有 `ProviderSmokeTester` 做连通检查、`questionary` 做箭头选择（核心逻辑与 TUI 分离以便测试）。B 新增 `PaperSectionWriter`（LLM 按 section 写 LaTeX 论述）+ `markdown→LaTeX` 清洗 + 语言贯通 + 指标表格 + 从 source registry 生成 `references.bib`；保留 claim/evidence 作为事实骨架与 trace。

**Tech Stack:** Python 3.12、typer/rich、questionary（需加入依赖）、现有 providers/smoke、agents/{writer,paper_sections,paper_context,claim_planning}、tectonic、pytest、ruff。

---

## Part 0：论文为何远未达到可提交水平（根因调查）

真跑（2026 MCM C，中文论文）渲染出的 PDF 暴露以下问题，均已定位到代码：

| 现象（PDF 可见） | 根因（代码） |
|---|---|
| 引言倒灌 `Confirmed Direction User Mode ai_led Output Language zh Data Strategy…` | `paper_sections._render_introduction` 直接用 `context.direction_summary`，而它 = `paper_context._summarize_markdown(discussion/confirmed_direction.md)`，把内部 artifact 各字段拍平成 run-on 文本 |
| Model 段 `**M1:**`/`** 模型形式 **` 字面星号 | LLM 输出 markdown，`_summarize_markdown` 只去 `#`；插入 LaTeX 时无 markdown→LaTeX 转换 |
| Model 决策内容**重复两遍** | `_render_claim_section("model.tex")` 先插 `context.model_decision_summary`，`claim_planning._model_claims` 的 claim_text 又把同一段 `model_decision_summary` 拼进去 |
| Results 是英文流水账 `Metric elimination_consistency_rate equals 0.2647…` | `claim_planning._metric_claims` 每条 evidence 生成一句英文 claim（evidence 的 `claim` 字段），逐句渲染；无表格、无论述、无语言适配、下划线字段名未处理 |
| 中文论文里 Assumptions/Sensitivity/Conclusion 整段英文 | `writer.SECTION_CONTENT` 与 `claim_planning` 各 claim 文本、`_render_introduction` 末句均为**硬编码英文**；语言贯通只覆盖了 abstract lead 与 problem-understanding 正文 |
| 参考文献为空 | `writer._write_main_files` 写死 `references.bib` 桩；未从 source registry/citation 生成条目 |
| 摘要末句混英文 | abstract 第二行取 critical claim 文本，而 claim 文本是英文模板 |

**结论：** 论文由"**raw artifact 字段 + 逐指标 claim**用**英文模板字符串拼接**"而成，只有 Model 段有真实 LLM 内容（且未清洗）。可追溯性（claim/evidence/trace）是对的，但**可读正文质量**这一层基本不存在。Part B 即重写这一层。

---

## Part A：交互式 /api（箭头选择 + 查看/输入 + 连通检查）

### A.0 目标交互
```
> /api
┌ API 配置 ─ ↑/↓ 选择, Enter 进入, q 退出 ───────────────┐
│ ▸ LLM         [ok]   deepseek-v4-flash                  │
│   Search      [missing]                                 │
│   MinerU      [missing]                                 │
│   Embedding   [missing]                                 │
│   Humanizer   [missing]                                 │
└────────────────────────────────────────────────────────┘
（进入某项后）
  1) 查看当前配置
  2) 输入/修改（隐藏输入 key；base_url/model）
  3) 测试连通  → 调 ProviderSmokeTester，显示 passed/failed+detail
  4) 返回
```

### A.1 设计要点（含需用户确认的决策）
- **TUI 库**：用 `questionary`（已安装，箭头选择最干净）。**需加入 `pyproject.toml` 依赖**。无 TTY（管道/测试）时回退到"编号菜单 + 行输入"。
- **核心/TUI 分离**：所有逻辑放可测核心 `ApiConsole`（纯函数式：给定 provider+动作+答案 → 读/写配置、跑连通检查、返回结构化结果）；`questionary` 只在真 TTY 下驱动核心。**测试只测核心**（注入答案，不依赖 TTY）。
- **连通检查**：复用 `ProviderSmokeTester.check(provider)`（真实轻量请求，已脱敏、写 history）。
- **写配置**：key→`.env`（`MAG_*`），base_url/model 等→`.mag/config.toml`，复用现有 `config.py` 读取映射。key 输入用 `questionary.password`（隐藏）。
- **provider 集合**：llm(required)、search(tavily/brave/exa/firecrawl)、mineru、embedding、humanizer。

### A.2 文件结构
| 文件 | 职责 | 动作 |
|---|---|---|
| `src/mcm_agent/core/api_console.py` | 可测核心：列状态、读/写单个 provider 配置、跑连通检查 | 新建 |
| `src/mcm_agent/core/config_writer.py` | 统一写 `.env` / `.mag/config.toml`（key→env, 其余→toml），带 upsert | 新建（抽出 init.py 现有写逻辑） |
| `src/mcm_agent/cli_commands/api.py` | `/api`：有 TTY→questionary 驱动；无参→保留只读状态；`--no-tui` 回退编号菜单 | 改写 |
| `pyproject.toml` | 加 `questionary>=2.0` | 改 |
| `tests/test_api_console.py` | 核心：状态、写配置、连通检查（mock smoke） | 新建 |
| `tests/test_config_writer.py` | env/toml upsert | 新建 |

### A.3 任务（TDD）
- [ ] **A-T1 config_writer**：`set_secret(root, "MAG_LLM_API_KEY", v)` upsert 到 `.env`；`set_config(root, "llm", "model", v)` upsert 到 `.mag/config.toml`。测试：重复写覆盖、不破坏其他键、`load_settings` 能读到。
- [ ] **A-T2 ApiConsole.status(root)**：返回 `[{provider, configured, detail, model?}]`，从 `load_settings` 推。测试：未配/已配两态。
- [ ] **A-T3 ApiConsole.set_provider(root, provider, answers)**：把 answers（key/base_url/model）经 config_writer 落盘。测试：llm 三项落到 env+toml；search 落 key。
- [ ] **A-T4 ApiConsole.test_provider(root, provider, tester=None)**：默认构造 `ProviderSmokeTester(load_settings(root))`，调 `.check(provider)`，返回 passed/failed/detail（detail 脱敏）。测试：注入 fake tester 返回 passed/failed。
- [ ] **A-T5 ApiCommand TUI**：有 TTY→questionary 主菜单（select provider→action）；无 TTY→保留现状态文本 + 提示 `/api` 在终端可交互。测试：`--no-tui` 或注入 answers 路径跑核心，不进 questionary。
- [ ] **A-T6**：`pyproject` 加 questionary；`pytest -q && ruff` 绿；提交 `feat: interactive /api with arrow-key select and connectivity test`。

> 注：questionary 真 TTY 行为不在单测覆盖（无 TTY）；用 `scripts/` 手动 smoke + 真机验证。

---

## Part B：论文质量重写（LLM section-writer + 清洗 + 语言 + 表格 + 参考文献）

### B.0 设计原则
- **每个 section 由 LLM 写论述**，输入=该 section 的结构化事实（题意要点、模型决策要点、真实指标、图表、来源、claim），输出=**目标语言的 LaTeX 正文**；claim/evidence 仍作事实骨架并保留 trace 注释（可追溯不变）。
- **编译-修复循环（用户确认）**：① markdown→LaTeX 清洗 + LaTeX 转义；② 编译失败时，把 tectonic 报错日志 + 出错 section 回喂 LLM 让其**修正 LaTeX 并重编译，循环直到通过**（有限次，如 ≤4）；③ 仅当修复重试耗尽仍失败，才用确定性 fallback section 兜底并显著记录（保证无人值守也能出 PDF）。
- **彻底语言贯通**：所有 section（含 fallback、claim 文本、trace 可见句）随论文语言；专有名词允许英文。
- **不再倒灌**：禁止把 `confirmed_direction.md` 等内部 artifact 原文拼进正文；只把"要点"喂给 LLM。

### B.1 文件结构
| 文件 | 职责 | 动作 |
|---|---|---|
| `src/mcm_agent/core/latex_text.py` | `markdown_to_latex(text)`（`**b**`→`\textbf`、`*i*`、`-`列表、去 `###`、code fence）+ `latex_escape_text`（`& % # _ $ ^ ~ \`，保护 `$..$` 数学） | 新建 |
| `src/mcm_agent/agents/section_writer.py` | `PaperSectionWriter(llm, language)`：`write_section(name, facts)→LaTeX`；失败/无 LLM→fallback | 新建 |
| `src/mcm_agent/agents/writer.py` | 用 section_writer 产出 abstract/intro/assumptions/model/results/sensitivity/conclusion；保留 claim trace 注释；调清洗 | 改写 |
| `src/mcm_agent/agents/paper_sections.py` | 退为"事实打包 + fallback 渲染 + trace"，不再拼 raw summary | 改 |
| `src/mcm_agent/agents/paper_context.py` | summary 改为"结构化要点"（不拍平 artifact）；新增 metrics 读取 | 改 |
| `src/mcm_agent/agents/reference_manager.py` | 从 source_registry/citation_candidates 生成真实 `references.bib`；无来源时空文献节而非桩 | 改 |
| `src/mcm_agent/agents/claim_planning.py` | metric claim 改为"结构化指标项"（名/值/含义），不写死英文句 | 改 |
| 测试 | 见各任务 | 新建/改 |

### B.2 任务（TDD）
- [ ] **B-T1 latex_text 清洗**：`markdown_to_latex` 处理 `**bold**`→`\textbf{}`、`*it*`→`\emph{}`、`- ` 列表→itemize、去 `#`/code fence；`latex_escape_text` 转义特殊字符但保护 `$...$`。测试覆盖：星号、下划线、百分号、数学保护、列表。
- [ ] **B-T2 PaperSectionWriter**：给定 facts（dict）与 language，构造 prompt，调 LLM 产出该 section LaTeX；强制以 `\section{...}`/`\section*{}` 开头、经 B-T1 清洗与转义；无 LLM 或异常→确定性 fallback（语言感知）。测试：fake LLM 返回 markdown→输出无 `**`、含 `\section`；无 LLM→fallback 语言正确。
- [ ] **B-T3 metrics → 表格 + 论述**：Results 由真实 `model_metrics.json` 生成 `tabular` 指标表 + LLM 一段解读（含义、是否符合预期），中文论文用中文表头。测试：metrics→含 `\begin{tabular}` 与指标名；无下划线裸字段（转义）。
- [ ] **B-T4 references.bib 真实化**：`reference_manager` 从 source registry 生成 `@misc/@online` 条目；claim 的 `\cite` key 对齐；无来源→不放空 `\bibliography` 桩导致的孤儿。测试：给 2 条来源→bib 2 条目、key 匹配。
- [ ] **B-T5 writer 重写 + 去重 + 语言**：abstract/intro/assumptions/model/results/sensitivity/conclusion 全走 section_writer；删除 model 决策重复；引言不再倒灌 direction_summary；全 section 语言贯通。测试：中文 run（fake LLM）→各 section 中文 fallback、无 `Confirmed Direction`、model 段不重复。
- [ ] **B-T6 编译-修复循环**：tectonic 编译失败→把报错日志+出错 section 回喂 LLM 修正→重编译，循环 ≤4 次直到通过；耗尽后用确定性 fallback 兜底。测试：注入一段"坏 LaTeX" + fake LLM 返回修正版→循环后编译通过（tectonic 在则真编，不在则 mock 编译器按"修正后通过"断言）。
- [ ] **B-T7 真题回归**：真跑 2026 MCM C（中/英各一），渲染 PDF 人工核对：无倒灌、无 `**`、无混语、Results 有表格、参考文献有条目。
- [ ] **B-T8**：`pytest -q && ruff` 绿；分多次提交（latex_text→section_writer→metrics→references→writer 重写→repair）。

### B.3 验收（可提交观感）
- 中文论文：摘要/引言/假设/模型/结果/敏感性/结论**全中文论述**（专名英文），无机器字段、无 markdown 星号、无重复段。
- Results 有指标**表格 + 解读**，不是流水账。
- 参考文献有真实条目（有来源时）。
- 中/英两种语言均可编译出 PDF。
- 现有测试不回归（当前 439）。

---

## 推荐执行顺序与拆分
- 两部分独立，可并行；建议先 **B-T1/B-T2/B-T3**（最影响观感），再 A（交互体验），再 B 其余。
- 每个 T 单独提交、推 main；每完成 B 的关键阶段用真题回归一次。

## 需用户确认的决策
1. **A 的 TUI 库**：用 `questionary`（推荐，加依赖）还是不加依赖的纯编号菜单？
2. **A 连通检查**：用真实 smoke（会发一次轻量真请求/有极小成本）确认通断——确认可接受？
3. **B 范围**：本轮是否一次做全 7 个 section 的 LLM 重写（推荐），还是先做最差的 intro/results/conclusion？
4. **B 编译安全网**：是否接受"LLM section 编译失败→自动回退确定性 fallback section"这一兜底策略（保证总能出 PDF）？
