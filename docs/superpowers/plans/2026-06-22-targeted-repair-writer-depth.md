# 靶向修复 + 写作做深 + 评委去噪 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 把 mag 论文质量从「结构完整但空泛」推向「有实质、靶向收敛」——三件事:(A) O6 重跑改为**靶向修复**(把评委批评喂回修复阶段);(B) 写作器**做深**(每节 提纲→实质草稿→自修订,且用完整 ModelSpec 接地);(C) 评委**去噪**(多次取均值,让靶向路由稳定)。

**Architecture:** 复用现有 26 阶段引擎与 O6 闭环。新增:`MockJudge.score_consensus`(去噪);O6 写 `review/repair_directive.json`(弱维+批评+目标阶段);`paper_writer`/`solver_coder` 读取并注入该指令;`PaperSectionWriter` 升级为多遍 + 接受 `exemplars`(KB seam,默认空,契约见 `2026-06-22-mag-kb-integration-contract.md`);writer 用完整 ModelSpec+指标+校验接地 model/results/sensitivity 节。

**Tech Stack:** Python 3.12;provider 接口 `generate(system, prompt)->ProviderResult(content)`(不改);现有 MockJudge / GateDecision / StageExecutor。

## Global Constraints
- **不改 provider 接口**;多遍写作 = 多次 `generate` 调用。
- **向后兼容 + 降级**:无 LLM → 现有确定性 fallback;`exemplars` 默认空 = 行为同现状;无 `repair_directive.json` → 修复阶段照常跑。**现有 742 测试必须全绿。**
- **KB seam 只留接口、不接实现**(本计划不依赖 KB;`exemplars: list[str]=[]`)。
- **防伪造**:写作 prompt 仍禁编造数字;数字来自真实 ModelSpec/指标。
- **终止性**:不得引入新的不收敛循环;O6 的 MAX_ITERS/keep-best 保持不变。
- 仅提交 `src/`/`tests/`/`docs/`;**绝不 `git add -A`**(`assets/` 版权);提交信息结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;直接提交+推 main。
- 测试用 fake LLM(参考 `tests/test_mock_judge.py::_JudgeLLM`、`tests/test_llm_agents.py::StaticLLMProvider`);**不**起真 kernel/真 LLM。

## 文件结构
- 改 `src/mcm_agent/agents/mock_judge.py`(+ `score_consensus`)
- 改 `src/mcm_agent/agents/mock_judge_gate.py`(用 consensus + 写 repair_directive.json)
- 改 `src/mcm_agent/agents/section_writer.py`(多遍 + exemplars)
- 改 `src/mcm_agent/agents/writer.py`(完整 ModelSpec 接地 + 读 repair_directive 注入对应节)
- 改 `src/mcm_agent/agents/solver.py`(读 repair_directive 注入解题 prompt)
- 测试:`tests/test_mock_judge.py`、`tests/test_mock_judge_gate.py`、`tests/test_section_writer.py`(新或扩)、`tests/test_llm_agents.py`/writer 测试、`tests/test_solver_interpreter_loop.py`

---

## Task C1: MockJudge 去噪(consensus 评分)

**Files:** Modify `src/mcm_agent/agents/mock_judge.py`; Test `tests/test_mock_judge.py`

**Interfaces — Produces:** `MockJudge.score_consensus(self, paper_text, *, figure_count=0, language="en", samples=3) -> RubricScore`：调用 `self.score(...)` `samples` 次,**每维取均值后四舍五入为 int**;`comments`/`revision_suggestions` 取「最接近均值总分的那次」的(或合并去重,取并集前若干)。无 LLM 时 `score` 已是确定性 heuristic → consensus 等于单次(samples 折叠为 1,避免空跑)。

- [ ] **Step 1: 失败测试** `test_score_consensus_averages_dimensions`:fake LLM 依次返回三组 dims(如某维 [2,4,6] → 均值 4);断言 `score_consensus(samples=3).dimensions[dim]==4`;且无 LLM 时 `score_consensus` == `score`(同 heuristic)。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** `score_consensus`:`if self.llm is None: return self.score(...)`;否则跑 `samples` 次收集 RubricScore,`dims[d]=round(mean(scores[i].dimensions[d]))`,选 `comments`/`suggestions` 来自 `min(scores, key=lambda s: abs(s.total-mean_total))`。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_mock_judge.py -q`
- [ ] **Step 5: 提交** `feat: MockJudge.score_consensus averages N judge samples (denoise) [C]`

---

## Task A1: O6 写靶向修复指令 + 用 consensus

**Files:** Modify `src/mcm_agent/agents/mock_judge_gate.py`; Test `tests/test_mock_judge_gate.py`

**Interfaces — Consumes:** `MockJudge.score_consensus`(C1)。**Produces:** 当 O6 判 `needs_repair` 时,额外写 `review/repair_directive.json`：
```json
{"target_stage": "<repair_stage>", "weak_dimension": "<dim>", "score": <int>,
 "critique": "<comments[dim] or ''>", "suggestions": ["...","..."], "iteration": <int>}
```
当 O6 判 `pass` 时,**删除** `review/repair_directive.json`(若存在),避免陈旧指令污染后续。

- [ ] **Step 1: 失败测试** 扩 `test_mock_judge_gate.py`：低 figures → 除 needs_repair/repair_stage 外,断言 `review/repair_directive.json` 存在且 `weak_dimension=="figures"`、`target_stage=="figure_planning"`、含 `critique`/`suggestions`;高分 pass → 断言 repair_directive.json **不存在**(或被删)。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**：`MockJudgeGateAgent.run` 用 `MockJudge(self.llm_provider).score_consensus(...)` 取代 `score`;在 needs_repair 分支用 `write_json` 写 repair_directive.json(critique 取 `score.comments.get(weak_dim,"")`,suggestions 取 `score.revision_suggestions[:3]`);在 pass 分支 `directive=workspace_root/"review"/"repair_directive.json"; directive.unlink(missing_ok=True)`。返回值列表加上 `review/repair_directive.json`。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_mock_judge_gate.py -q`(含 keep-best、MAX_ITERS 仍绿)
- [ ] **Step 5: 提交** `feat: O6 emits review/repair_directive.json with weak-dim critique [A]`

---

## Task A2: 修复阶段消费靶向指令(paper_writer + solver_coder)

**Files:** Modify `src/mcm_agent/agents/writer.py`、`src/mcm_agent/agents/solver.py`;新增 helper `src/mcm_agent/core/repair_directive.py`;Tests `tests/test_solver_interpreter_loop.py` + writer 测试

**Interfaces — Produces:** `core/repair_directive.py::read_repair_directive(workspace_root) -> dict | None`(读 `review/repair_directive.json`,不存在返回 None,坏 JSON 返回 None)。
- `solver.py`：若指令存在且 `target_stage=="solver_coder"`,把 `f"评委反馈(需重点修复 {weak_dimension}={score}): {critique}. 建议: {suggestions}"` 注入求解 prompt（`_subproblem_prompt` 与一次性 `base_prompt` 顶部都加,作为 "PRIOR JUDGE FEEDBACK" 段）。
- `writer.py`：若指令存在且 `target_stage=="paper_writer"`,把指令塞进它命中的那一节的 facts(`facts["judge_feedback"]={dimension, critique, suggestions}`);dim→节映射沿用 O6 的 `DIM_TO_STAGE` 反推(modeling/mathematics/writing/coherence/summary_sheet/problem_coverage 各对应的 .tex 节;无法精确映射时塞给所有非表格节)。

- [ ] **Step 1: 失败测试**
  - solver:`tests/test_solver_interpreter_loop.py` 加 `test_solver_injects_repair_directive`:写 `review/repair_directive.json`(target_stage=solver_coder, weak=data_solution),用脚本化 LLM 断言传给 `generate` 的 prompt 含 "PRIOR JUDGE FEEDBACK" 与 critique 文本。
  - writer:写 directive(target_stage=paper_writer, weak=writing),断言写作器对应节的 facts 含 `judge_feedback`(可在 `_facts_for_section` 层断言,或注入后检查传给 section_writer 的 facts)。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** `read_repair_directive` + solver 注入 + writer `_facts_for_section`/section 循环注入。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_solver_interpreter_loop.py tests/test_solver_codegen.py -q` + writer 测试
- [ ] **Step 5: 提交** `feat: solver+writer consume repair_directive for targeted repair [A]`

---

## Task B1: PaperSectionWriter 多遍(提纲→实质→自修订)+ exemplars seam

**Files:** Modify `src/mcm_agent/agents/section_writer.py`; Test `tests/test_section_writer.py`(新建或扩)

**Interfaces — Produces:** `PaperSectionWriter.write_section(self, name, title, facts, *, exemplars: list[str] | None = None) -> str`(签名加 `exemplars`,默认 None=空,KB seam)。LLM 路径改为三遍:
1. **outline**:`generate(system, _outline_prompt(name,title,facts,exemplars))` → 详细提纲文本。
2. **draft**:`generate(system, _draft_prompt(name,title,facts,outline,exemplars))` → 实质 LaTeX 正文(方程解释、假设论证、结果解读;若 facts 含 `judge_feedback` 必须针对性修复)。
3. **revise**:`generate(system, _revise_prompt(name,title,draft))` → 自评本节负责的 rubric 维后改一版。
最终经 `markdown_to_latex` + `_ensure_header`;任一遍异常/空 → 退化到下一可用产物(有 draft 用 draft;全失败用 `_fallback`)。`exemplars` 注入 prompt 时附"仅模仿结构与详尽度,不得复制句子/数字"。

- [ ] **Step 1: 失败测试** `test_section_writer_three_pass`:计数 fake LLM(记录调用次数与各次 prompt)→ 断言 `write_section` 触发 3 次 generate;第 2 次 prompt 含第 1 次产出的 outline;最终正文非空且比单次 fallback 长。`test_section_writer_falls_back_without_llm`:无 LLM → 确定性 fallback(不变)。`test_section_writer_injects_judge_feedback`:facts 含 `judge_feedback` → draft prompt 含其 critique。`test_exemplars_appear_in_prompt`:传 exemplars → outline/draft prompt 含之 + 防抄袭语。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** 三遍 + prompt 构造 + 降级 + exemplars/judge_feedback 注入。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_section_writer.py tests/test_llm_agents.py -q`
- [ ] **Step 5: 提交** `feat: multi-pass section writer (outline->draft->revise) + exemplars seam [B]`

---

## Task B2: writer 用完整 ModelSpec + 指标 + 校验接地深度节

**Files:** Modify `src/mcm_agent/agents/writer.py`; Test writer 测试(`tests/test_llm_agents.py` 或 `tests/test_abstract_coherence.py` 同目录新增)

**Interfaces — Consumes:** `read_model_spec`、`flatten_metrics`、`validation_report`。**Produces:** `_facts_for_section` 对 `model`/`results`/`sensitivity` 节传**完整 ModelSpec 子问题**(title/approach/variables/assumptions/equations(LaTeX)/algorithm_steps/metrics,而非薄摘要)+ 真实 flatten 指标 + `reports/validation_report.md` 摘要,并把 B1 的 `exemplars`(空)+ A2 的 `judge_feedback` 一并带上;section 循环把 `exemplars` 透传给 `write_section`。

- [ ] **Step 1: 失败测试** `test_model_section_facts_include_full_spec`:构造含 variables/equations/algorithm_steps 的 ModelSpec → 断言 `_facts_for_section("model",...)` 的 facts 含 equations 与 algorithm_steps(不仅 title/approach);`test_results_facts_include_real_metrics`:断言 results facts 含 flatten 后的真实指标键。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** 扩 `_model_facts_from_spec`/`_facts_for_section` 带全字段;section 循环传 `exemplars=[]`(seam)。
- [ ] **Step 4: 跑测通过 + 全量回归** `pytest -q`(**全绿硬门**)
- [ ] **Step 5: 提交** `feat: ground model/results/sensitivity sections in full ModelSpec+metrics+validation [B]`

---

## Task V: 真题 e2e + 去噪 MockJudge 前后对比(验证,不改产品码)

- [ ] 装真 deepseek-v4-pro,跑 MCM-C 真题全流水线(含 O6 靶向闭环)。
- [ ] 用 §findings 的真实-judge 评分法(`load_settings(config_file=...)` + `score_consensus`)记录 10 维分,与 1.5 基线对比,重点看 writing/modeling/coherence/coverage 是否随靶向修复单调上升。
- [ ] 把新基线 + 产物写进 memory `project_real_paper_engine.md` 与 `assets/b5_runs/`(不提交 assets)。

---

## Self-Review
- **覆盖**:A=A1+A2(靶向指令+消费);B=B1+B2(多遍写作+完整接地);C=C1(去噪);KB=B1 的 exemplars seam(契约对齐,不接实现)。
- **占位扫描**:每步有真实代码意图 + 真实断言,无 TODO。
- **类型一致**:`score_consensus`、`write_section(..., exemplars=)`、`read_repair_directive`、`repair_directive.json` 字段在引用处一致。
- **降级/终止**:exemplars 空=现状;无 directive=现状;三遍任一失败逐级降级;O6 终止性不变;全程不引入新循环。

## Execution Handoff
Subagent-Driven:顺序 C1 → A1 → A2 → B1 → B2 → V。C1/A1 改 judge 侧,A2/B1/B2 改 writer+solver 侧;A2 与 B1/B2 都改 writer.py,故 **A2 在 B1 后、B2 前**或合并注意冲突——按 C1→A1→B1→A2→B2 执行(B1 先扩签名,A2 再注入 judge_feedback,B2 收口接地)。每组推 main。
