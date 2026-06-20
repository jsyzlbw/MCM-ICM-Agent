# mag 接下来的工作 · 计划书（O 奖论文质量 + CLI 客户端服务端）

- 日期：2026-06-20
- 用途：研究全部设计文档 + 当前代码实况后，给出**分优先级、可连续执行 6 小时以上**的前进计划，供讨论后夜间自动执行。
- 研究依据：`docs/superpowers/specs/2026-06-20-o-prize-roadmap.md`、`2026-06-19-mag-real-paper-engine-design.md`、`docs/03/06/07-*.md`、代码审计（mvp.py / writer / solver / visualization / validation / mock_judge…）。

---

## 0. 北极星 & 现状一句话
- **北极星**：AI 全自动（AI 提议、人审）产出**美赛 O 奖级论文**；现实中间里程碑 = 稳定 Finalist/M 奖且有冲 O 的机会。
- **量尺**：`mock_judge.py` 的 10 维 rubric（summary_sheet / problem_coverage / modeling / mathematics / data_solution / validation / sensitivity / figures / writing / coherence），`scripts/score_paper.py` 可跑。
- **当前基线**：LLM MockJudge ≈ **4.7/10**（figures=1 最低、coherence=3、writing=4、validation 低）。离线启发式 5.6/10。
- **两条前进线**：
  - **A · 论文质量（北极星，可量化）** —— 审计给出 7 个有明确修法的缺口，多数 S/M，且都能用 MockJudge + e2e 验证。**最适合夜间自动执行。**
  - **B · CLI 客户端/服务端重构** —— 你已选「完整客户端/服务端」，但它 UX 敏感、靠你终端反馈（这轮已多次需要你截图），且 socket/async 不易夜间无人验证。**建议有人时再做。**

---

## 1. 现状关键事实（审计结论）
- **引擎**：`StageExecutor` 驱动 `workflows/mvp.py::_mvp_stage_handlers` 固定图；gate 失败→repair 重跑；崩溃也会尽力出稿（不硬崩）。
- **模型一致性（O1，部分已做）**：`ModelDesignAgent.run` 出 `ModelSpec` → `SolverCoderAgent` 据此生成/执行代码（≤3 自修复）→ `refine_from_code` 用真实代码回写 spec。指标 `flatten_metrics` 注册为 evidence。
- **图（O4，未做关键一步）**：`VisualizationAgent` 渲染 pdf/svg/png 到 `figures/` 并通过 `FigureQualityAgent`，**但没有任何阶段把图 `\includegraphics` 进 .tex** → 编出的 PDF **零图** → judge 只读文字、figures 打 1 分。**这是最低分项且修法机械明确。**
- **摘要↔模型不一致（coherence=3）**：`writer._facts_for_section` 的 abstract 用 `model_decision_summary`（解题前的选择），model 用代码反推的 `ModelSpec` → 两者可能描述不同方法。
- **语言串味（writing=4）**：`ReviewerAgent._fallback_review/_generate_review`、`paper_sections.py` 兜底句硬编码中英混排，不随论文语言变。
- **无 MCM 摘要页（O5 未做）**：所谓 summary sheet 只是 `\section*{Abstract}`；main.tex 无控制号/标题/首页一页纸摘要。
- **校验只查管线完整性（validation 低、质量不稳）**：`ValidationAgent` 只查"指标有证据/产物存在/无缺输出"，**不查结果合理性**——`elimination_consistency_rate=0.0` 也能过 → 论文质量 run-to-run 漂移大。
- **敏感性靠自由代码生成（常空）**：无确定性兜底；缺失时只写空表头、不拦。
- **MockJudge 未接入工作流（O6 未做）**：只在 `scripts/score_paper.py` 用；引擎从不给自己打分、不据分迭代。
- **CLI**：已有 `MagFullScreenApp` 全屏 TUI（带 `suppress_live_output`/`_io_ask` 桥 hack）；另有一套 **FastAPI 浏览器 GUI 服务**（`mag gui`，uvicorn 8787，`server/static/`）。新「客户端/服务端」plan 是另起 **TCP socket 事件内核**（与 FastAPI 那套不冲突，未来可共用）。

---

## 2. 夜间自动执行批次（推荐）：O 奖论文质量跃升
> 目标：把 MockJudge 从 ~4.7 推到 **6.5–7+**；每项 TDD + 单测，批次末做一次真题 e2e 并用 MockJudge 前后对比记录新基线。按价值/依赖排序；前几项是"低分项快赢"。

### PQ1 · 图表嵌入正文（目标 figures 1→~6）— effort M ★最高单项杠杆
- **改**：`agents/writer.py`（`_section_extras` 或 `_write_claim_plan_sections` 新增一步）读 `figures/figure_registry.json`，对 `used_in` 命中本节的图，追加
  `\begin{figure}[htbp]\centering\includegraphics[width=0.85\linewidth]{../figures/<id>.pdf}\caption{<caption_intent>}\label{fig:<id>}\end{figure}` + 正文 `\ref`；`_write_main_files` 加 `\graphicspath{{../figures/}}`。
- **校验**：`FigureQualityAgent`/`ReviewerAgent` 增"图必须被 .tex 引用"检查——渲染了但没嵌入 → 拦。
- **测试**：给定含图记录的 workspace，断言 main.tex/section .tex 出现 `\includegraphics` 且数量≥图数；编译产物非零图。
- **量尺**：figures 维显著上升。

### PQ2 · 摘要↔模型一致（目标 coherence 3→~6）— effort S ★小修大收益
- **改**：`agents/writer.py::_facts_for_section`，`name=='abstract'` 且 `model_spec.subproblems` 存在时，approach 由 ModelSpec 派生（join 子问题 title/approach）而非 `model_decision_summary`，并带 `flatten_metrics` 真实指标。
- **测试**：构造 ModelSpec=优化反演 + model_decision_summary=贝叶斯，断言 abstract facts 用的是 ModelSpec 的方法词。

### PQ3 · 结果可信度门（validation + 质量稳定）— effort M ★治 run-to-run 漂移
- **改**：`agents/validation.py` 增"主指标合理性"检查：从 `ModelSpec.metrics` 取主指标，断言有限且落在合理区间（如 consistency/acc/R² ∈ [lo,1]、非 NaN）；失败 → gate `status=fail`、`repair_stage=solver_coder`（重解）。可选：重解 N 次取最优。
- **测试**：主指标=0.0/NaN → 拦并路由重解；落在区间 → 过。

### PQ4 · 确定性敏感性兜底（sensitivity 质量）— effort M
- **改**：`agents/solver.py` 增确定性兜底：对一个关键参数/输入做网格扰动重算主指标，写 `results/sensitivity_analysis.csv`（≥3 行），保证每次 run 都有真实 sweep；`writer` 在有行时必渲染敏感性表。
- **测试**：无 LLM 路径也产出 ≥3 行 sensitivity csv；writer 渲染出表。

### PQ5 · 语言纯度（目标 writing 4→~6）— effort M
- **改**：`ReviewerAgent._fallback_review/_generate_review` 标题/正文按论文语言参数化；`paper_sections.py` 兜底句复用 `section_writer._FALLBACK` 的中英成对版；`TypesettingQAAgent` 加"异语种行" lint，命中 → 路由 `paper_writer` 重写。
- **测试**：zh 论文的评审报告与兜底节无英文 boilerplate；en 论文反之。

### PQ6 · MCM 摘要页 Summary Sheet（O5）— effort M
- **改**：新 `agents/summary_sheet.py`（或扩 writer）产首页块：控制号占位 + 题目 + **一页纸 LLM 摘要**（问题重述/方法/关键真实指标/结论，区别于技术 abstract）；模板入 `templates/paper`，`main.tex` 首个 `\input`。
- **测试**：main.tex 含摘要页块 + 控制号占位；摘要含真实指标数字。

### PQ7 · MockJudge 修订环（O6）— effort L ★把量尺接进闭环（夜间 stretch）
- **改**：typesetting 后、final_gatekeeper 前加 `mock_judge` 阶段：`MockJudge(llm).score(read_paper(ws))` → 写 `review/mock_judge_scores.json`（含历史曲线）→ 按维生成 revision_suggestions 路由 repair（figures→figure_planning、coherence→paper_writer、validation→solver_coder），循环到收敛或 max 迭代上限。
- **测试**：低维触发对应 repair 路由；分数历史单调或封顶停。
- 注：effort L，若夜间时间不够，作为 stretch；PQ1–6 + PQ8 已是扎实一夜。

### PQ8 · 真题 e2e + 前后评分对比（验证）— effort S
- 跑完整 MCM-C 流水线，`scripts/score_paper.py` 前后各评一次，记录新基线到 `project_real_paper_engine.md`；把 PDF/分数留作晨间汇报。

**夜间推荐顺序**：PQ2(快)→PQ1(最高杠杆)→PQ3→PQ4→PQ5→PQ6→PQ8(中途 e2e 看涨幅)→PQ7(capstone，时间允许)。每项 TDD+复审+提交；按组推 main。

---

## 3. 另一条线（建议有人时做）：CLI 客户端/服务端
- 详见 `2026-06-20-mag-client-server-cli.md`。阶段：S1 协议+事件总线(M) → S2 核心 I/O 事件化(M) → S3 TCP server+client(L) → S4 TUI 转客户端、删 hack(M) → S5 协议文档+trace(S) → S6 GUI 接入示例(S)。
- **为何不放夜间**：UX 敏感（每次界面改动都靠你真终端反馈+截图）、socket/async 出问题难无人验证、与现有 FastAPI GUI 需协调。**S1–S2（事件解耦、纯逻辑、可单测）其实可安全夜间做**——如果你更想推这条，我可以夜间只做 S1–S2（拿到"解耦修坑"主收益，不碰 socket/UI），S3–S4 等你在场。

---

## 4. 夜间执行方式 & 安全约束
- 子代理逐任务：每任务 实现(TDD)→复审→修→提交；按组 `git push origin main`（你的常驻指令"逐段同步 main"）。
- 仅提交 `src/`/`tests/`/`docs/`；**绝不** `git add -A`（`assets/` 版权题目永不提交）；keys 在 `.env`（gitignored）。
- 每项以现有 553 测试为底线全绿 + 新增针对性测试；论文类改动以真题 e2e + MockJudge 前后对比验证。
- 不做破坏性/不可逆操作；晨间留一份清晰汇报（做了什么、分数变化、PDF、遗留项）。
- 进度记 `.superpowers/sdd/progress.md`（断点可续）。

---

## 5. 风险
| 风险 | 缓解 |
|---|---|
| LLM 真题 e2e 慢/偶发网络 | 单测用 fake provider 离线；e2e 失败自动重试+记录，不卡整夜 |
| MockJudge LLM 评分有噪声 | 同时记录离线启发式分；多次取均值；关注维度相对变化而非绝对值 |
| 某项改动触发 gate 连锁 | 沿用 RepeatedGateFailureError 尽力出稿；每项独立提交，可回退 |
| O6(PQ7) 体量大 | 作为 stretch，时间不够则跳过，不影响 PQ1–6 收益 |

---

## 6. 我的建议（待你拍板）
**夜间跑 A 批次（PQ1–PQ8，论文质量）**：最贴北极星、可量化、自验证、不依赖你的实时 UX 反馈，一夜能把论文从"能跑通"推向"像样且分数明显上升"。CLI 客户端/服务端留到你在场一起推（或夜间只做其纯逻辑的 S1–S2）。
