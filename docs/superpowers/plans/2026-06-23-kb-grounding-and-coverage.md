# 知识库接入 + 覆盖可靠性 实施计划（item 2 + 3）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** (2) 把已发布的 451 篇 O 奖知识库接进引擎当力量倍增器:① 建模器吃「题型范式卡」(无需嵌入);② 写作器吃「真实 O 奖同节范例」(Voyage 嵌入检索)。(3) 修覆盖可靠性:让建模阶段稳定地把题目**每个子问题**都拆出来(现在时灵时不灵,真跑常只出 1 个)。配套 item 1 的裁判锚校准(独立脚本,已先跑)。

**Architecture:** 复用 `corpus/retrieve.py`(`section_exemplars`/`methods_for_problem_type`)+ `patterns/<type>.json` + `taxonomy.problem_type` + B1 已留的写作器 `exemplars` seam。全部**可选 + 优雅降级**:KB 缺失 / 无 Voyage / 检索返回 [] → 行为同现状(契约 `docs/superpowers/specs/2026-06-22-mag-kb-integration-contract.md`)。

**Tech Stack:** 现有 ModelDesignAgent / PaperWriterAgent / PaperSectionWriter(三遍,带 exemplars 入参)/ corpus retrieve / Voyage(已配)。

## Global Constraints
- **可选 + 降级(硬约束)**:每处 KB 消费用 try/except + 空回退;`kb_dir` 取 `settings.corpus_kb_dir`(默认 corpus_kb);无库/无 key/检索空 → 不报错、按现状跑。现有 ~788 测试全绿。
- **防抄袭注入纪律**:范例只作「结构/深度」参照,prompt 必须含「模仿组织与详尽度,不得复制句子/数字/具体内容,本题内容须原创」。
- **不伪造**;仅提交 src/tests/docs/scripts;**绝不 git add -A**;提交结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;推 main。
- 测试**不连真 Voyage/真 LLM**:用 fake embedding/reranker + 内存或临时 chroma,或直接 stub `section_exemplars`/`methods_for_problem_type` 注入假命中;断言「prompt 含范例文本 + 防抄袭语」与「无库时不崩」。

## 文件结构
- `src/mcm_agent/core/problem_type.py`(新,problem_type 解析:taxonomy + LLM 兜底)
- `src/mcm_agent/agents/model_design.py`(COV 可靠分解 + KB 范式卡注入)
- `src/mcm_agent/agents/writer.py`(写作器填 exemplars seam)
- 对应 tests + `scripts/calibrate_judge.py`(item1,已建)

---

## Task COV1: 可靠的子问题枚举（item 3，先做——它是上 M 的硬门槛）

**Files:** Modify `src/mcm_agent/agents/model_design.py`; Test `tests/test_model_design*.py`

**诊断:** `_design` 一次性「枚举任务 + 设计模型」,LLM 常合并成 1 个。改为**两段 + 校验**。

**Interfaces — Produces:**
- `ModelDesignAgent._enumerate_tasks(understanding: str) -> list[str]`:一次**只做枚举**的 LLM 调用,返回题目所有显式任务/子问题的短标题列表(prompt:"List EVERY distinct task/sub-question the problem asks, as a JSON array of short titles. Contest problems usually have 3–5. Do not merge or omit.")。解析失败 → `[]`。
- `_design` 改为:先 `tasks = self._enumerate_tasks(understanding)`;把 tasks 作为「必须各自成为一个 subproblem 的清单」注入设计 prompt;`_normalize_spec` 后**若 `len(subproblems) < len(tasks)` 且 tasks 非空 → 重试一次**(更强指令 + 显式 task 列表);仍不足 → 至少**用 tasks 补齐缺失的 subproblem**(用 task 标题建占位 subproblem,approach 由 LLM 或兜底填),保证 subproblem 数 ≥ 识别出的任务数。无 LLM → 现状 fallback。

- [ ] **Step 1: 失败测试**
  - `test_enumerate_tasks_returns_list`:fake LLM 返回 `["estimate fan votes","compare methods","partner effect","fairer system"]` → `_enumerate_tasks` 返回长度 4。
  - `test_design_backfills_to_task_count`:fake LLM 枚举出 4 个 task,但设计调用只返回 1 个 subproblem → `_design`/`run` 后 spec.subproblems 长度 ≥ 4(补齐),每个 task 标题都出现在某 subproblem。
  - `test_design_prompt_lists_enumerated_tasks`:断言设计 prompt 含枚举出的 task 文本。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** `_enumerate_tasks` + 两段设计 + 重试 + 补齐。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/ -k model_design -q`
- [ ] **Step 5: 提交** `feat: reliable sub-question enumeration — design one subproblem per task with backfill [#3 COV1]`

---

## Task KB0: problem_type 解析（KB 注入的前置）

**Files:** Create `src/mcm_agent/core/problem_type.py`; Test `tests/test_problem_type.py`

**Interfaces — Produces:** `resolve_problem_type(workspace_root, llm=None) -> str | None`:
- 若 `reports/problem_meta.json` 或题目能给出 (year, letter) → `taxonomy.problem_type(year, letter)`。
- 否则若有 llm → 让 LLM 从 problem_understanding 选一个 taxonomy 类型词(continuous/discrete/data/operations_research/sustainability/policy/interdisciplinary),落 `reports/problem_type.json`。
- 解析不出 → None。永不抛。

- [ ] **Step 1: 失败测试** `test_resolve_problem_type_from_taxonomy`(给 year/letter)+ `test_resolve_problem_type_none_when_unknown`(无信息+无llm→None,不崩)。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**(复用 `corpus/taxonomy.py::problem_type`)。
- [ ] **Step 4: 跑测通过 + 回归**
- [ ] **Step 5: 提交** `feat: problem_type resolver (taxonomy + LLM fallback) [#2 KB0]`

---

## Task KB1: 建模器吃题型范式卡（item 2，无需嵌入）

**Files:** Modify `src/mcm_agent/agents/model_design.py`; Test model_design 测试

**Interfaces — Consumes:** `resolve_problem_type`(KB0)、`corpus_kb/patterns/<type>.json`。**Produces:** `_design`(枚举后)读 `settings.corpus_kb_dir/patterns/<problem_type>.json`,把 `common_models`/`common_techniques`/`recurring_pitfalls`/`reusable_patterns` 摘要注入设计 prompt 作「同题型获奖论文的常用方法与坑」参照(防抄袭语:借鉴方法范式,不照搬)。无库/无该类型文件 → 不注入(现状)。kb_dir 经 settings(ModelDesignAgent 需能拿到 settings 或 kb_dir;若拿不到,加可选 `kb_dir` 构造参数,默认 None=禁用)。

- [ ] **Step 1: 失败测试** `test_design_injects_pattern_card`:临时 kb_dir 写 `patterns/data.json`(含 common_models 等)+ problem_type=data → 断言设计 prompt 含某 common_model 名;`test_design_no_pattern_card_graceful`:无库 → 不崩、不注入。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** 读 pattern 卡 + 注入 + 降级。
- [ ] **Step 4: 跑测通过 + 回归**
- [ ] **Step 5: 提交** `feat: modeler grounded in problem-type pattern card from KB [#2 KB1]`

---

## Task KB2: 写作器吃真实 O 奖同节范例（item 2，Voyage 嵌入）

**Files:** Modify `src/mcm_agent/agents/writer.py`; Test writer 测试

**Interfaces — Consumes:** `corpus/retrieve.py::section_exemplars(kb_dir, query, *, section, embedding_provider, reranker, problem_type, top_k)`、`provider_bundle.embedding/.reranker`、`resolve_problem_type`。**Produces:** 写作器 section 循环对每节调用 `section_exemplars`(query=本节意图,section=映射的 section_type〔abstract→summary,model→model,results→results,sensitivity→sensitivity,...〕,problem_type=resolved,top_k=2),取命中的 `.content` 作 `exemplars` 传给 `write_section(..., exemplars=...)`(B1 seam)。全程 try/except:无 embedding/无库/检索空 → `exemplars=[]`(现状)。kb_dir 经 settings。

- [ ] **Step 1: 失败测试** `test_writer_passes_section_exemplars`:stub `section_exemplars` 返回 1 条假范例(monkeypatch)→ 断言传给 PaperSectionWriter.write_section 的 exemplars 非空且含该范例文本;`test_writer_exemplars_graceful_without_kb`:retrieve 抛错/无 embedding → exemplars=[],不崩,正常出稿。(用 recording PaperSectionWriter 或断言其入参。)
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** section→section_type 映射 + 检索 + 传 seam + 降级。
- [ ] **Step 4: 跑测通过 + 全量回归** `pytest -q`(全绿硬门)
- [ ] **Step 5: 提交** `feat: writer grounds sections in real O-paper exemplars via KB retrieval [#2 KB2]`

---

## Task V: 真题 e2e + 校准对比
- [ ] deepseek-v4-pro + Voyage 跑 DWTS 全流水线;断言子问题数 ≥ 题目任务数(COV1 生效)、设计 prompt 用了范式卡、写作命中范例。
- [ ] 全文 consensus 真实裁判评分 + 与 item1 的「真实 O 奖均分」对比(gap 是否缩小);记 memory + `assets/b5_runs/`。

## Self-Review
- 覆盖:item1 校准(脚本已建)、item2(KB1 范式卡 + KB2 范例,KB0 前置)、item3(COV1 可靠分解)。
- 降级:每处 KB 消费 try/except + 空回退;无 Voyage/无库均不崩;COV1 无 LLM 走 fallback。
- 类型一致:resolve_problem_type、section_exemplars 入参、exemplars seam、kb_dir(settings.corpus_kb_dir)贯穿一致。

## Execution Handoff
Subagent-Driven 顺序:**COV1 → KB0 → KB1 → KB2 → V**。COV1/KB1 都改 model_design.py(COV1 先);KB2 改 writer.py。每组推 main;KB2 后全量回归。
