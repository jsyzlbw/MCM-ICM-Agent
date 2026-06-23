# 锚定式相对评委（修可信的尺子）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** 把 MockJudge 从「凭空 0–10 绝对打分」改成**锚定真实 O 奖论文的相对评分 + 证据绑定**,让真实 O 奖在我们尺子上稳定 ≥8、且能区分质量。背景:校准证明现尺倒挂(真 O≈4.5 < mag 7.0)——尺子坏了,O6 在优化「骗分」。决策(用户已定):锚定相对评分;参照源 = **teardown 卡 + markdown 片段结合**。

**Architecture:** 新增「参照块」检索(teardown 卡按 problem_type 过滤〔无需嵌入〕+ section markdown 片段〔Voyage〕);MockJudge 锚定模式:给评委一段真实 O 奖参照,打「相对 O」分 + 每维引用候选论文证据;figures 维从候选自身判(参照丢图,不比)。`calibrate_judge.py` 升级为**验收回归**:真 O 必须 ≥8、且 mag 不得 ≥ 真 O。全部**优雅降级**:无 KB/无 Voyage/检索空 → 退回现绝对评委(明确标注"未校准")。

**Tech Stack:** 现有 MockJudge / corpus.retrieve.section_exemplars / corpus_kb/teardowns / resolve_problem_type / Voyage(已配)。

## Global Constraints
- **降级硬约束**:`kb_dir`/`embedding` 缺失或检索抛错 → 锚定模式不可用 → 退回现 `_system`/`_prompt` 绝对评委,RubricScore.comments 标 `"_mode":"absolute(uncalibrated)"`;锚定成功标 `"_mode":"anchored"`。现有 ~811 测试全绿。
- **不把被评论文当自己的参照**:`exclude_paper_id` 必须从参照集中剔除(校准时尤其重要)。
- **不伪造**;测试**不连真 Voyage/真 LLM**:stub 参照检索 + fake judge llm,断言「prompt 含参照 + 相对档位 + 证据要求」与「无 KB 时退回绝对模式」。
- 仅提交 src/tests/docs/scripts;**绝不 git add -A**;提交结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;推 main。

## 文件结构
- `src/mcm_agent/corpus/reference.py`(新:build_reference_block)
- `src/mcm_agent/agents/mock_judge.py`(锚定模式 + 绝对回退)
- `src/mcm_agent/agents/mock_judge_gate.py`(把 kb_dir/embedding/problem_type 传给 MockJudge)
- `scripts/calibrate_judge.py`(锚定模式 + 验收断言)
- 对应 tests

---

## Task J1: 参照块检索（teardown 卡 + markdown 片段）

**Files:** Create `src/mcm_agent/corpus/reference.py`; Test `tests/corpus/test_reference.py`

**Interfaces — Produces:** `build_reference_block(kb_dir, problem_type, *, query="", embedding=None, reranker=None, exclude_paper_id=None, max_teardowns=2, max_excerpts=2) -> str`:
- **teardown 部分(无需嵌入)**:遍历 `kb_dir/teardowns/*.json`,取 `problem_type` 匹配、`paper_id != exclude_paper_id` 的前 `max_teardowns` 张,摘出 `models_used / why_it_won / pitfalls_or_limitations / reusable_patterns` 拼成简短文本。
- **markdown 片段部分(Voyage,可选)**:若 `embedding` 提供,`section_exemplars(kb_dir, query or "modeling approach and results", section="model", embedding_provider=embedding, reranker=reranker, problem_type=problem_type, top_k=max_excerpts)`,取 `.content` 前 ~800 字/条;剔除 `exclude_paper_id` 命中。
- 拼成一段带标题的「REFERENCE: real Outstanding work for this problem type」块。**任何失败 → 返回已成功的部分;全失败 → ""**(never raise)。

- [ ] **Step 1: 失败测试** `test_build_reference_block_teardowns`(tmp kb 写 2 张 data teardown → 块含 why_it_won 文本、不含 exclude 的那张);`test_build_reference_block_no_embedding_teardown_only`(无 embedding → 只 teardown,不崩);`test_build_reference_block_empty_when_no_kb`(空 kb → "")。
- [ ] **Step 2: 跑确认失败**
- [ ] **Step 3: 实现**(teardown 过滤 + 可选 section_exemplars + 拼接 + try/except)。
- [ ] **Step 4: 跑通过 + 回归** `pytest tests/corpus/test_reference.py -q`
- [ ] **Step 5: 提交** `feat: KB reference-block builder (teardown cards + section excerpts) [judge J1]`

---

## Task J2: MockJudge 锚定相对评分模式

**Files:** Modify `src/mcm_agent/agents/mock_judge.py`; Test `tests/test_mock_judge.py`

**Interfaces — Produces:**
- `MockJudge(llm_provider=None, *, kb_dir=None, embedding=None, reranker=None)`(新增 keyword-only 锚定依赖,默认 None=绝对模式)。
- `score(paper_text, *, figure_count=0, language="en", problem_type=None, exclude_paper_id=None) -> RubricScore`:若 `kb_dir`&`problem_type` 有 → `ref = build_reference_block(...)`;`ref` 非空 → 用**锚定 prompt**(见下),comments 加 `{"_mode":"anchored"}`;否则退回现绝对 prompt + `{"_mode":"absolute(uncalibrated)"}`。
- 锚定 prompt(`_anchored_system` + `_anchored_prompt`):给出 REFERENCE 块,要求:`9–10 = 达到/超过参照的严谨与完整;7–8 = 明显强但不及参照;5–6 = 合格;≤4 = 弱`;**每维必须引用候选论文的具体内容作证据,只有声明无实质 → 低分**;`figures` 维**只按候选自身的 figure_count 与图相关内容判,不与(丢图的)参照比`;保留完整性硬门(A/T)。输出 JSON 同现格式。
- `score_consensus` 透传新 kwargs(problem_type/exclude_paper_id)。

- [ ] **Step 1: 失败测试** `test_anchored_mode_uses_reference`(monkeypatch `build_reference_block`→返回"REF: model=Bayesian, won because rigor";fake judge llm 记录 prompt → 断言 prompt 含该参照文本 + "9-10" 相对档位 + "evidence"/"cite" 证据要求 + comments._mode=="anchored");`test_absolute_fallback_without_kb`(无 kb_dir → 用现绝对 prompt,_mode含"absolute");`test_anchored_falls_back_on_empty_ref`(ref 返回"" → 绝对模式,不崩)。
- [ ] **Step 2: 跑确认失败**
- [ ] **Step 3: 实现** 锚定 system/prompt + 模式选择 + comments 标注 + 降级。保留 `_heuristic`(无 llm)。
- [ ] **Step 4: 跑通过 + 回归** `pytest tests/test_mock_judge.py tests/test_mock_judge_gate.py -q`
- [ ] **Step 5: 提交** `feat: MockJudge anchored relative scoring vs real-O reference + evidence-grounded [judge J2]`

---

## Task J3: 接线 O6 gate + 校准脚本升级为验收回归

**Files:** Modify `src/mcm_agent/agents/mock_judge_gate.py`, `scripts/calibrate_judge.py`; Test `tests/test_mock_judge_gate.py`

**Interfaces — Produces:**
- `MockJudgeGateAgent.__init__` 增 `kb_dir/embedding/reranker`(可选);`run` 里 `resolve_problem_type(workspace_root, llm)` → 传给 `MockJudge(llm, kb_dir=, embedding=, reranker=).score_consensus(..., problem_type=ptype)`。mvp.py 的 mock_judge_gate 阶段传 `settings.corpus_kb_dir`(存在才传)+ `provider_bundle.embedding/reranker`。
- `calibrate_judge.py`:锚定模式(传 kb_dir/embedding + 每篇 `exclude_paper_id=该篇`,避免拿自己当参照);打印真 O 均分;**加 `--assert-min`(默认 8.0):真 O 均分 < 阈值则非零退出**(验收回归)。

- [ ] **Step 1: 失败测试**(gate)`test_gate_passes_kb_to_judge`:构造带 kb_dir/embedding 的 gate + stub MockJudge 记录收到的 kwargs → 断言 problem_type/kb_dir 被传入;`test_gate_works_without_kb`(无 kb → 仍跑,绝对模式,现有 O6 测试全绿)。
- [ ] **Step 2: 跑确认失败**
- [ ] **Step 3: 实现** gate 接线 + mvp 传参 + calibrate 锚定 + --assert-min。
- [ ] **Step 4: 跑通过 + 全量回归** `pytest -q`(全绿硬门)
- [ ] **Step 5: 提交** `feat: O6 gate + calibration use anchored judge; calibrate asserts real-O>=8 [judge J3]`

---

## Task J-V: 重跑校准验收 + mag 复评（真机)
- [ ] 锚定模式重跑 `python scripts/calibrate_judge.py --per-type 2`(+ Voyage):**真 O 应 ≥8**(锚定把它顶上去);否则锚定/prompt 需调。
- [ ] 用锚定评委复评 V e2e 的 mag 论文 → 拿**诚实的 gap-to-O**(预计远低于旧 7.0)。记 memory + `assets/b5_runs/`。
- [ ] 这才是「现在离 O 多远」的可信数。

## Self-Review
- 覆盖:J1 参照块(teardown+markdown 结合,用户定)、J2 锚定相对评分+证据绑定、J3 接 O6+校准回归、J-V 验收。
- 降级:无 KB/Voyage/检索空 → 绝对模式(标注);figures 不比丢图参照;exclude_paper_id 防自参照。
- 类型一致:build_reference_block 签名、MockJudge 新 kwargs、score(problem_type/exclude_paper_id)、gate 传参 贯穿一致。
- 观念:输出仍是 0–10,但语义变为「相对真 O」;真 O≈9 是构造出来的锚 → mag 的分第一次有意义。

## Execution Handoff
Subagent-Driven 顺序:**J1 → J2 → J3 → J-V**。J2 依赖 J1;J3 依赖 J2。每组推 main;J3 后全量回归;J-V 真机(可与其他校准并行)。
