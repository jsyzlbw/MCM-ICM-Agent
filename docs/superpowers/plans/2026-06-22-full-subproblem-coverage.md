# 全子问题覆盖 + 裁判完整性 实施计划（#1 + #2）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** 让 mag **答全题**(MCM/ICM 多子问题各自深做),并让裁判**惩罚漏答**——这是从"成功参与"到 M/F 的硬门槛。诊断:DWTS 验证run只解了 4 问里的 1 问,因为 (a) `ModelDesignAgent` 有时只分解出 1 个子问题,(b) 求解器把所有东西写进单个 `problem1.py`,(c) `refine_from_code` 读那一个文件 → 把 spec 塌缩成 1 个子问题。

**Architecture:** 把"求解单元"从 problem1 改为**每个子问题**:`ModelDesignAgent` 忠实枚举题目每个任务为一个子问题;求解器对**每个子问题**写独立产物(`code/experiments/<sub_id>.py`、`results/<sub_id>_results.csv`、`model_metrics.json[sub_id]` 嵌套);`refine_from_code` **逐子问题**精修(不塌缩);写作器**每子问题一节深写**。外加 #2:裁判按"答了几问/共几问"扣 problem_coverage;修摘要页中文泄漏。

**Tech Stack:** 现有 ModelDesignAgent / SolverCoderAgent(CI 环)/ PaperWriterAgent / MockJudge / flatten_metrics(已支持嵌套 per-sub 指标)。

## Global Constraints
- **向后兼容**:单子问题时行为≈现状;`results/problem1_results.csv` 作为"首个子问题结果"的别名继续存在(figure_planning/validation 仍读它);`model_metrics.json` 改为嵌套 `{sub_id:{...}}`,`flatten_metrics` 已把嵌套展平为 `metric_<sub_id>_<name>`(evidence/validation/writer 走展平键)。
- **降级**:某子问题求解失败 → 记录、继续其余子问题(尽力出稿),不整体崩。无 LLM → 模板兜底(现状)。
- **不伪造**:每子问题指标来自其真实代码执行。
- 现有 ~775 测试全绿;仅提交 src/tests/docs;**绝不 git add -A**;提交结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;推 main。
- 测试不起真 LLM/真 kernel;用 fake provider + FakeCodeInterpreter。

## 文件结构
- `src/mcm_agent/agents/model_design.py`(忠实分解 + 逐子问题 refine)
- `src/mcm_agent/agents/solver.py`(逐子问题产物)
- `src/mcm_agent/agents/writer.py`(逐子问题 results)
- `src/mcm_agent/agents/mock_judge.py`(coverage 惩罚)
- `src/mcm_agent/agents/summary_sheet.py`(修中文泄漏)
- 对应 tests

---

## Task SC0a: 裁判惩罚漏答子问题(#2a，先做——修好量尺再测 #1)

**Files:** Modify `src/mcm_agent/agents/mock_judge.py`; Test `tests/test_mock_judge.py`

**Interfaces — Produces:** `_system()`/`_prompt()` 增强:裁判先**数出题目要求的任务数 T**(从论文里出现的子问题/问题分项),再数**实际有实质解答的任务数 A**,`problem_coverage` 必须按 `A/T` 给分——**漏答要狠扣**(显式指令:"If the paper addresses only some of the problem's required tasks, problem_coverage MUST be scaled down proportionally; a paper answering 1 of 4 tasks scores problem_coverage <= 3 regardless of how well that one task is done"). 同时 `revision_suggestions` 要点名"未解答的任务"。

- [ ] **Step 1: 失败测试** `test_coverage_penalizes_partial`:fake 裁判这里没法真判 LLM,改为**断言 prompt/system 文本含完整性指令**(包含 "tasks"/"proportionally"/"only some" 这类关键短语 + problem_coverage 与任务数挂钩的措辞)。即测 prompt 构造,不测 LLM 判断。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** 在 `_system`/`_prompt` 加完整性评分指令(英文)。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_mock_judge.py tests/test_mock_judge_gate.py -q`
- [ ] **Step 5: 提交** `feat: judge penalizes unaddressed sub-tasks in problem_coverage [#2a]`

---

## Task SC0b: 修摘要页中文/markdown 泄漏(#2b)

**Files:** Modify `src/mcm_agent/agents/summary_sheet.py`; Test `tests/test_summary_sheet*.py`

**Interfaces — Produces:** 摘要页标题/restatement 不再混入 `problem_understanding.md` 的原始 markdown 标题与"# 题意理解报告 ## 题目背景"等脚手架。修法:取 problem_title/restatement 时,**剥离以 `#` 开头的行、去掉"题意理解报告/题目背景"这类报告脚手架词**,只取干净的题目描述首句;若 ModelSpec.problem_restatement 为空,用清洗后的 problem_understanding 正文首句,而非原始带标题文本。

- [ ] **Step 1: 失败测试** `test_summary_sheet_no_markdown_or_report_scaffold`:构造 problem_understanding.md = `# 题意理解报告\n## 题目背景\nThe problem is about DWTS...`(+ 空 restatement)→ 生成摘要页 → 断言 summary_sheet.tex **不含** `# 题意理解报告`/`## 题目背景`/裸 `#` 标题,但含 "DWTS"。
- [ ] **Step 2: 跑测确认失败**(当前泄漏)
- [ ] **Step 3: 实现** 清洗函数(去 `^#.*` 行 + 去脚手架词)用于 title/restatement 取值。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/ -k summary_sheet -q`
- [ ] **Step 5: 提交** `fix: summary sheet title strips markdown headings + report scaffold [#2b]`

---

## Task SC1: ModelDesignAgent 忠实枚举题目每个任务为子问题(#1)

**Files:** Modify `src/mcm_agent/agents/model_design.py`; Test `tests/test_model_design*.py`

**Interfaces — Produces:** `_design` 的 prompt 强化:**先从题目里逐条列出所有显式任务/子问题(Q1,Q2,…),为每个任务设计一个 subproblem**;明确"每个被问到的任务都必须成为一个 subproblem,不得合并或遗漏"。`problem_understanding.md` 若已列出子问题,作为枚举依据。保持 `_normalize_spec` 不变。

- [ ] **Step 1: 失败测试** `test_design_prompt_demands_one_subproblem_per_task`:断言 `_design` 传给 LLM 的 prompt/system 含"one subproblem per task / list every task / do not merge or omit"类指令。(测 prompt;LLM 输出用既有 fake。)再加:给一个 fake LLM 返回 4 个子问题 → 断言 spec.subproblems 长度 4(走 _normalize_spec)。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** prompt 强化。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/ -k model_design -q`
- [ ] **Step 5: 提交** `feat: model design enumerates one subproblem per problem task [#1]`

---

## Task SC2: 求解器逐子问题产物(#1 核心)

**Files:** Modify `src/mcm_agent/agents/solver.py`; Test `tests/test_solver_interpreter_loop.py`

**Interfaces — Produces:** `_run_interpreter_loop` 改为**逐子问题**:对每个 `sub`(用 `sub.subproblem_id`,无则 `q{i}`):
- 子问题 prompt 要求写 `results/<sub_id>_results.csv` 与**该子问题**的指标(任务专属键)。
- 该子问题 ReAct 结束后:把其成功执行的代码写 `code/experiments/<sub_id>.py`;把其指标读出并存入嵌套 `model_metrics.json[sub_id] = {...}`(累积,不互相覆盖)。
- **别名兼容**:把第一个子问题的结果 CSV 同时复制到 `results/problem1_results.csv`(figure_planning/validation 仍依赖),并保留 `code/experiments/problem1.py` = 第一个子问题代码(refine 兼容)。
- 成功判据:`model_metrics.json` 为非空 dict 且至少一个子问题有真实指标。`_record_outputs` 用 `flatten_metrics`(已展平嵌套)登记 evidence。
单子问题时退化为现状(sub_id 命名变化但行为一致)。

- [ ] **Step 1: 失败测试** `test_interpreter_loop_writes_per_subproblem_outputs`:ModelSpec 含 2 子问题(q1,q2);脚本化 LLM 为每个子问题写 `results/<sub_id>_results.csv` + 各自指标(用 FakeCodeInterpreter 真 exec);断言 `code/experiments/q1.py` 与 `q2.py` 都存在,`model_metrics.json` 形如 `{"q1":{...},"q2":{...}}`,且 `results/problem1_results.csv` 作为 q1 别名存在。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** 逐子问题产物 + 嵌套指标 + 别名 + per-sub 代码持久化。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_solver_interpreter_loop.py tests/test_solver_codegen.py -q`
- [ ] **Step 5: 提交** `feat: solver produces per-subproblem code+results+nested metrics [#1]`

---

## Task SC3: refine_from_code 逐子问题精修(不塌缩)(#1)

**Files:** Modify `src/mcm_agent/agents/model_design.py`; Test `tests/test_model_design*.py`

**Interfaces — Consumes:** `code/experiments/<sub_id>.py` 集合 + `model_metrics.json[sub_id]`。**Produces:** `refine_from_code` 枚举 `code/experiments/*.py`(排除非子问题文件),对每个文件调用 LLM 精修出**一个** subproblem(用文件名 stem 作 sub_id),把所有精修结果**汇总成多子问题 spec**(不再只读 problem1.py 塌缩成 1 个)。无 per-sub 文件时回退读 problem1.py(现状,单子问题)。

- [ ] **Step 1: 失败测试** `test_refine_from_code_keeps_all_subproblems`:workspace 有 `code/experiments/q1.py` 与 `q2.py` + 嵌套 metrics;fake LLM 每次返回 1 子问题;断言精修后 spec.subproblems 长度 ==2(各自 sub_id),而非 1。
- [ ] **Step 2: 跑测确认失败**(当前只读 problem1.py)
- [ ] **Step 3: 实现** 逐文件精修 + 汇总;保留单文件回退。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/ -k model_design -q`
- [ ] **Step 5: 提交** `feat: refine_from_code refines each subproblem's code without collapsing [#1]`

---

## Task SC4: 写作器逐子问题深写 results(#1)

**Files:** Modify `src/mcm_agent/agents/writer.py`; Test writer 测试

**Interfaces — Produces:** results 节 facts 按子问题分组:`{"per_subproblem":[{"subproblem": title, "approach":..., "metrics": <该 sub 的指标>}, ...], "instruction": "每个子问题各自解读其指标与拟合优劣"}`(从嵌套 model_metrics.json + model_spec 子问题派生)。model 节已逐子问题(保留)。3-pass 写作器据此为每个子问题写出独立解读。(单子问题时等价现状。)

- [ ] **Step 1: 失败测试** `test_results_facts_grouped_by_subproblem`:嵌套 metrics `{"q1":{...},"q2":{...}}` + 2 子问题 spec → 断言 results facts 含 `per_subproblem` 且长度 2,每项带其 metrics。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** results facts 按 sub 分组(从嵌套 metrics 读;扁平 metrics 时退回现状单组)。
- [ ] **Step 4: 跑测通过 + 全量回归** `pytest -q`(全绿硬门)
- [ ] **Step 5: 提交** `feat: writer gives each subproblem its own results treatment [#1]`

---

## Task SC-V: 真题 e2e 验证(覆盖 + 分数)
- [ ] deepseek-v4-pro 跑 DWTS 全流水线;断言 `model_spec.json` 子问题数 ≈ 题目任务数(≥3),`code/experiments/` 有多个 `<sub_id>.py`,论文 results/model 各子问题都有实质段落。
- [ ] 全文 consensus 真实裁判评分(coverage 现在会惩罚漏答);与 7.0(单问)对比——目标是 coverage 真实化后**总分在"答全题"下仍≥7 且 coverage 不再虚高**。记 memory + `assets/b5_runs/`。

## Self-Review
- 覆盖:#2a(裁判完整性)+#2b(摘要泄漏)+#1(SC1 分解 / SC2 逐子求解 / SC3 逐子精修 / SC4 逐子写作)。
- 兼容:problem1 别名 + 嵌套 metrics(flatten 已支持)+ 单子问题回退,均保旧测试绿。
- 降级:子问题失败不整崩;无 LLM 模板兜底。
- 类型一致:sub_id 贯穿 solver/refine/writer;model_metrics 嵌套 `{sub_id:{}}`;flatten_metrics 展平键不变。

## Execution Handoff
Subagent-Driven 顺序:**SC0a → SC0b → SC1 → SC2 → SC3 → SC4 → SC-V**。SC2/SC3 是核心且耦合(per-sub 产物 ↔ per-sub 精修),SC3 紧接 SC2。每组推 main;SC4 后全量回归。
