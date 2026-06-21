# 让 mag 在「数学建模写作」领域超越 MathModelAgent 与通用 Agent · 战略与证明计划

- 日期：2026-06-21
- 作者：Bill + Claude（Opus 4.8）
- 用途：给出一份**可落地**的能力路线图，让 mag 在 MCM/ICM 论文生成这一垂直领域**实测超过** (a) 专用竞品 MathModelAgent（jihe520）与 (b) 通用 Agent（Claude Code / Codex / Hermes）；并设计一套**经得起推敲的实验**来证明这一点。
- 研究依据：本轮对 MathModelAgent backend 全量源码审计、mag 自身代码/设计文档审计、以及 LLM-agent 评测方法学调研（见文末附录 A 的原始结论）。
- 北极星不变：AI 全自动（AI 提议、人审）产出**美赛 O 奖级论文**；现实中间里程碑 = 稳定 Finalist/M 且有冲 O 的机会。
- 配套动作：默认模型切换到 **deepseek-v4-pro**（见 §5 模型策略）。

> 本文是**战略 + 实验设计**文档，不是逐任务 TDD 计划。每个能力支柱给出「改什么 / 为何能超越 / 在哪段代码 / 工作量 / 验收量尺」，可直接转成 writing-plans 的实施计划再落地。**先看、先拍板，不直接做。**

---

## 0. 一页纸结论（TL;DR）

**竞品真相（本轮最重要的发现）**：MathModelAgent 官网/README 宣传的「四层容错、Evaluator Shadow Mode、Feedback Rerun、HIL 六动作、RAG 知识库」**绝大部分没有实现**——README「后期计划」自己标了未勾选 + 代码里只有 TODO 注释和配置桩。MMA **真正落地**的只有四件事：① 真·有状态 Code-Interpreter 求解环（Jupyter/E2B 持久 kernel + .ipynb）；② 高质量领域 prompt（建模决策树、coder/writer 规范）；③ 每个 agent 独立选模型；④ 强制把图插进论文 + OpenAlex 真引用。它**没有** rubric、没有评估器、没有模型↔代码↔叙述一致性校验、没有 PDF 编译、没有 benchmark。

**这意味着我们的取胜路径异常清晰**：
1. **补上 MMA 唯一的真优势**——把 mag 的「一次性生成代码」升级为**有状态 Code-Interpreter 求解环**（支柱 A）。这是 mag 当前与 MMA 唯一的实质差距。
2. **造出 MMA 只敢宣传、没敢做的闭环质量引擎**——rubric 驱动的自评→定向重跑（O6）+ 多模态看图自评 + 成功路径正确性校验（支柱 B）。这是 mag 反超 MMA 的**护城河**。
3. **守住通用 Agent 没有的垂直工程**——图入正文、一页纸 Summary Sheet、敏感性/校验硬门、证据-论断绑定、编译出 PDF（支柱 C/D/F）。通用 Agent 一次过写一篇「像论文的文档」，但拿不出**跑过真代码的真实数字 + 编译通过的投稿级 PDF + 按评分迭代过的稿子**。
4. **用一套预注册、双盲、锚定真实 O/M/F 论文、独立评审团 + 配对统计**的实验，把「超越」做成可证伪的数字结论（§7）。

**一句话战略**：*MMA 把质量闭环写在 README 里，我们把它写进代码里；通用 Agent 写「像论文的文字」，我们交「跑过真数据、编译成 PDF、按 O 奖 rubric 迭代过的论文」。*

---

## 1. 战场与对手画像（审计结论）

### 1.1 MathModelAgent —— 真实能力 vs 宣传
| 能力 | 宣传 | 真实状态（源码审计） | 对我们的含义 |
|---|---|---|---|
| 有状态 Code-Interpreter | ✅ | ✅ **真做了**：`coder_agent.py` 单工具 `execute_code` ReAct 环，持久 Jupyter/E2B kernel，全 cell 落 `.ipynb` | **这是唯一要追平的真优势**（支柱 A） |
| 错误反思重试 | ✅ | ⚠️ **只在报错时**反思（`get_reflection_prompt`）；成功路径**从不**问「结果对不对」（`get_completion_check_prompt` 是死代码） | 我们在成功路径做正确性自评 → 反超点 |
| 四层容错 / Evaluator Shadow / Feedback Rerun | ✅ 头条特性 | ❌ **未实现**：README 后期计划未勾选；无 evaluator agent、全代码 `rubric` 0 命中；只有 `MAX_RETRIES`/`MAX_CHAT_TURNS` 计数 | **mag 已有 MockJudge rubric**，把它接成闭环即领先 |
| HIL 六动作（confirm/edit/regenerate/ask/skip/abort） | ✅ | ❌ **只有 abort**（cancel_event）；其余是 schema/config 桩，`workflow.py` 0 个暂停审批点 | 我们做真 HITL gate → 领先 |
| RAG 知识库（ChromaDB+rerank） | ✅ | ❌ backend `RAG_ENABLED=False`，无检索代码；Tavily 也没做，仅 Writer 有 OpenAlex | 我们已装 chromadb，做方法/代码模板检索 → 领先 |
| 多模型按 agent 选 | ✅ | ✅ 真做了（`LLMFactory` 4 套独立配置，litellm + 原生 Anthropic） | 追平即可（支柱 E） |
| 图→论文 + 真引用 | ✅ | ✅ Writer 强制 `![](file)` + ≥3 行分析 + OpenAlex `search_papers` | mag 当前**反而落后**（图没入正文）→ 先补齐（PQ1） |
| 看得见自己的图 | — | ❌ **对图盲**：图输出被替换成「[图片已生成，未展示]」，靠 prompt 让模型 print 数字描述 | **多模态看图自评是结构性反超点**（支柱 B） |
| 模型↔代码↔叙述一致 | — | ❌ 三段字符串传递，无校验，写手「别编数字」靠自觉 | mag 已有 `refine_from_code`，强化为可追溯 → 护城河 |
| 出 PDF / 排版校验 | — | ❌ backend 只拼接出 `res.md`，无 Typst/LaTeX 编译、无编号一致性/图引用校验（「9 步验收 + 17 模板」只在另一套 SKILLS 重写里） | **mag 已能编译 PDF**，是现成护城河（支柱 F） |
| Benchmark | 计划 | ❌ 未实现 | 我们做 benchmark 即可量化证明（§7） |

**结论**：MMA 是一个工程务实、prompt 优秀、但**质量闭环全靠宣传**的项目。它的护城河窄（CI 环 + prompt），且**对图盲、无评分、无一致性校验、不出 PDF**。

### 1.2 通用 Agent（Claude Code / Codex / Hermes）—— 强在哪、弱在哪
- **强**：底座模型强、会写代码、会写流畅英文、长上下文。给个好 prompt，能一次产出「读起来像论文」的长文。
- **弱（结构性）**：
  - 无 MCM 领域流水线：不会自动出**一页纸 Summary Sheet**、不会按 O 奖 rubric 自检、不强制图入正文、不做证据-论断绑定。
  - 无「先建模规格、后写代码、再回填规格」的纪律 → 数字常是**听起来合理但没真跑**。
  - 不天然编译出**投稿级 PDF**；排版/编号/图引用一致性靠运气。
  - 单次产出、无按分迭代。
- **对我们的威胁**：通用 Agent 的**文笔**可能不输我们。所以 mag 的取胜面**必须压在结构化、可验证、可追溯**这几条——「真跑过的数字、编译过的 PDF、按 rubric 迭代过的稿、充足且被正文引用的图、Summary Sheet、敏感性/校验硬证据」——这些是单次过的通用 Agent **稳定拿不全**的。

### 1.3 mag 现状（自审）
- 引擎：26 阶段 `StageExecutor` 固定图 + gate/repair 路由 + 尽力出稿（不硬崩）。
- 求解：**一次性 codegen + ≤3 崩溃自修复 + 模板兜底**（这是与 MMA 的核心差距）。
- 已有但未盘活的资产：`MockJudge`（10 维 rubric，**未接入闭环**）、`refine_from_code`（一致性回填）、`ValidationAgent`（合理性门，刚加）、确定性敏感性兜底、`chromadb` 依赖已装、**能编译 PDF**。
- 已知低分项：figures（图没入正文 → 1 分）、coherence、writing 语言串味、validation 不稳。
- 基线：LLM MockJudge ≈ 2.8–4.7/10（run-to-run 漂移大）。

---

## 2. 差异化定位（取胜楔子）

> **mag = 唯一真正闭环的、垂直于 MCM 的论文工厂。**

三条护城河，按「对手最难复制」排序：

1. **闭环质量引擎（vs MMA 的 PPT 护城河）**：rubric 自评 → 定向重跑 → 收敛。MMA 把这写进 README 却没写进代码；mag 已有 rubric 部件，接成环即领先一个身位。
2. **可验证的真实性（vs 通用 Agent 的「像论文」）**：每个出现在论文里的数字都能追溯到一次真实代码执行（证据-论断绑定 + 模型↔代码↔叙述一致性 + 成功路径正确性自评）。通用 Agent 给「合理的数字」，mag 给「跑出来的数字」。
3. **投稿级交付与垂直工程（vs 两者）**：编译通过的 PDF + 一页纸 Summary Sheet + 图入正文且被引用 + 敏感性/校验硬门 + 语言纯度。这些是 O 奖评委**第一眼**看的东西，而对手要么不做、要么做不全。

支撑这三条护城河，需要先**追平** MMA 的唯一真优势（有状态 CI 求解环）——否则「真实数字」无从谈起。所以路线图第一根支柱就是它。

---

## 3. 能力路线图：六大支柱

每根支柱标注：**改什么 / 为何超越 / 代码落点 / 工作量 / 验收量尺**。优先级见 §6 分期。

### 支柱 A · 有状态 Code-Interpreter 求解环（追平 MMA 唯一真优势）— ★最高杠杆
**现状**：`SolverCoderAgent._run_llm_codegen` 一次性写完整脚本 → 子进程跑 → 崩了才喂 traceback 修（≤3 次）。深度浅、无法「跑一步看一步、基于中间结果继续推进」。

**改什么**（核心重构，参考 MMA `coder_agent.py` + `local_interpreter.py`）：
- 新增 `tools/code_interpreter.py`：基于 `jupyter_client` 的**持久 kernel** 封装；`execute_code(code)->（stdout/执行结果/display_data/error, error_flag）`；每个 cell 追加进 `notebook.ipynb`（`nbformat`）；首次 `chdir(workspace)`、装 CJK 字体、清 matplotlib 缓存。**沙箱**：限时、限内存、禁网（白名单），workspace 隔离（mag 当前是裸 subprocess，要补隔离）。
- 重写 `SolverCoderAgent`：从「一次性 codegen」改为**单工具 ReAct 多轮环**——系统注入 `ModelSpec` 子问题 + 数据文件清单 → `while`：模型发 `execute_code` → 执行 → 把**真实 stdout/错误回灌** → 模型反思/续写下一步 → 直到「无工具调用 = 该子问题完成」。`MAX_TURNS`/`MAX_REPAIRS` 封顶；超限走确定性模板兜底（保留现有兜底）。
- **按子问题分段**（`add_section(subproblem_title)`）：每个 `ModelSpec.subproblem` 一段，kernel 状态跨段保留（前一问的清洗数据/中间变量可复用）——这正是「增量深解」的来源。
- **保留并强化** `refine_from_code`：环结束后用真实代码回写 `ModelSpec`，注册 `flatten_metrics` 为 evidence。

**为何超越**：
- vs MMA：**追平**其 CI 环；再叠加成功路径自评（支柱 B）和一致性回填（支柱 C），就**超过**它的「只在报错时反思」。
- vs 通用 Agent：通用 Agent 也能跑代码，但 mag 把执行结果**结构化绑进 ModelSpec/evidence**，数字进论文前必经校验——这是通用 Agent 的松散 REPL 给不了的。

**代码落点**：`src/mcm_agent/tools/code_interpreter.py`（新）、`src/mcm_agent/agents/solver.py`（重写 `_run_llm_codegen` 为 `_run_interpreter_loop`，保留 `_run_templated_baseline`/`_run_sensitivity_sweep` 兜底）、`workflows/mvp.py`（`solver_coder` 阶段接新环）。新依赖：`jupyter_client`、`ipykernel`、`nbformat`（加进 `pyproject.toml`）。

**工作量**：L（最大单项；建议拆 3–4 个 writing-plans 任务：kernel 封装 → 单工具环 → 分段+状态保留 → 兜底/沙箱）。

**验收量尺**：同一真题，新环 vs 旧一次性，MockJudge 的 `data_solution`/`mathematics`/`validation` 维显著上升；产出 `notebook.ipynb`（可复现）；主指标非平凡（非 0/NaN）。

---

### 支柱 B · 闭环质量引擎（MMA 只宣传没做的护城河）— ★反超核心
三个子件，合起来是「能给自己打分、能看见自己的图、能据此重跑」。

**B1 · MockJudge 修订环（O6）**——把量尺接进闭环。
- typesetting 后、final_gatekeeper 前加 `mock_judge` 阶段：`MockJudge(llm).score(read_paper(ws))` → 写 `review/mock_judge_scores.json`（含历史曲线）→ 低分维生成 `revision_suggestions` → **定向路由 repair**（`figures` 低 → `figure_planning`；`coherence` 低 → `paper_writer`；`validation`/`data_solution` 低 → `solver_coder`；`sensitivity` 低 → 敏感性兜底）→ 循环到收敛或 `max_judge_iters` 封顶。
- 代码落点：`workflows/mvp.py` 新阶段 + `agents/mock_judge.py`（已存在 scorer）。工作量 L。
- 验收：低维触发对应 repair；分数历史单调升或封顶停；e2e 总分较无环显著上升。

**B2 · 多模态看图自评**——攻 MMA 的「对图盲」。
- 渲染后，把每张图（PNG）喂给**多模态模型**（deepseek-v4-pro 若支持视觉，否则配一个视觉模型）问：标轴/图例/可读性/是否支撑论断/有无误导。低分 → 路由 `visualization` 重画；并把「看图所得」写进图注与正文分析（而不是像 MMA 只 print 数字）。
- 代码落点：`agents/figure_quality.py` 增视觉评审通道。工作量 M。
- 验收：能识别「缺轴标/图例缺失/空图」并拦截重画；`figures` 维超过仅靠数字描述的基线。

**B3 · 成功路径正确性自评**——攻 MMA「只在报错时反思」。
- 求解环每段成功后，调用 `get_completion_check`：主指标是否有限、量级是否合理、是否回答了该子问题、单位/符号是否自洽。不过关 → 续写修正（而非直接收尾）。
- 代码落点：`agents/solver.py` 求解环内（与支柱 A 同区）。工作量 M。
- 验收：构造「能跑通但结果离谱（如 consistency=0）」的用例 → 被自评拦下并重解。

---

### 支柱 C · 一致性与证据可追溯（vs 通用 Agent 的「像论文」）— 护城河
- **模型↔代码↔叙述一致**：强化 `refine_from_code`，建立 `evidence_registry` 的**强绑定**——论文里每个数字必须 `\ref` 一条 evidence id；`paper_evidence_binding` 阶段做审计，发现「正文出现未注册数字」→ 拦截路由 `paper_writer`。
- **摘要↔模型一致（PQ2）**：`writer._facts_for_section` 的 abstract 由**代码回填后的 ModelSpec** 派生（而非解题前的 `model_decision_summary`），带真实指标。工作量 S。
- 代码落点：`agents/writer.py`、`agents/validation.py`、`workflows/mvp.py::paper_evidence_binding`。工作量合计 M。
- 验收：注入「正文写了 R²=0.97 但 evidence 里没有」→ 被审计拦截；abstract 方法词与 ModelSpec 一致。

---

### 支柱 D · 垂直工程（O 奖评委第一眼看的东西）— 快赢，先做
- **D1 图入正文（PQ1）** ★最高单项性价比：`writer.py` 读 `figures/figure_registry.json`，对命中本节的图追加 `\includegraphics`+`caption`+`\label`+正文 `\ref`；`_write_main_files` 加 `\graphicspath`。校验：渲染了但没入正文 → 拦。工作量 M。验收：`figures` 维 1→6+，PDF 非零图。
- **D2 一页纸 Summary Sheet（PQ6）**：`agents/summary_sheet.py` 产首页（控制号占位 + 题目 + 问题重述/方法/关键真实指标/结论），`main.tex` 首个 `\input`。工作量 M。验收：含真实指标数字。
- **D3 结果可信度门（PQ3）**：`validation.py` 取主指标断言有限且落合理区间，失败 → `repair_stage=solver_coder`。工作量 M。验收：0.0/NaN 被拦。
- **D4 确定性敏感性兜底（PQ4）**：关键参数网格扰动重算主指标 → `results/sensitivity_analysis.csv`（≥3 行），writer 必渲染。工作量 M。验收：无 LLM 路径也有 ≥3 行。
- **D5 语言纯度（PQ5）**：`ReviewerAgent`/`paper_sections.py` 兜底句按语言参数化；`TypesettingQAAgent` 加异语种行 lint。工作量 M。验收：zh 论文无英文 boilerplate。

> D1–D5 = 已在 `2026-06-20-forward-plan` 里的 PQ1–PQ6，**仍然是性价比最高的快赢**，建议作为 P0 先落地（也为实验提供一个像样的基线）。

---

### 支柱 E · 模型与检索策略
- **E1 按 agent 选模型（追平 MMA）**：现已支持 `build_llm_provider`；扩成**每角色可独立配模型**——modeler/solver/judge 用 **deepseek-v4-pro**，writer 可配更强文笔模型，轻量阶段用 flash 省钱。落点：`settings` + `build_llm_provider` 支持 per-role 覆盖。工作量 M。
- **E2 默认切 deepseek-v4-pro**：`mcm_agent_config.local.json` 默认模型改 pro；保留 flash 作 A/B（见 §7 的 backbone 受控变量）。工作量 S。
- **E3 方法/代码模板检索（超 MMA 的未实现 RAG）**：用已装的 `chromadb` 建一个**建模方法 + 代码片段**知识库，在 `methodology_rag` 阶段给 modeler/solver 注入「vetted 方法卡 + 可跑代码模板」，降低幻觉。落点：`agents/methodology_rag.py` + `knowledge/`。工作量 L（可后置）。验收：检索命中率 + 求解环首轮成功率上升。

---

### 支柱 F · 投稿级交付（现成护城河，巩固）
- mag **已能编译 PDF**——这是 MMA backend（只出 markdown）和通用 Agent（不天然出 PDF）都缺的。要做的是**巩固**：编译失败必拦（不能静默出半成品）、编号/图引用/参考文献一致性 lint、页数/Summary Sheet 合规检查。落点：`agents/typesetting.py`、`pre_submission_review`、`final_gatekeeper`。工作量 M。验收：编译失败 100% 被拦并路由修复；产物是单一可投稿 PDF。

---

### 支柱 G（可选，有人时做）· 真 HITL 六动作（超 MMA 的桩）
- 在 `model_judge`（规格确认）、`validation_gate`、`final_gatekeeper` 三处加**真暂停点**：confirm / edit / regenerate / ask / skip / abort，复用 CLI 的 `_io_ask` 桥。MMA 只有 abort，我们做全 → 领先。工作量 M。**UX 敏感，建议你在场时做**（与 CLI 客户端/服务端那条线一起）。

---

## 4. 「超越」判定矩阵（每条对手 × 我们的取胜机制）

| 维度 | vs MathModelAgent | vs 通用 Agent | mag 取胜机制 |
|---|---|---|---|
| 求解深度 | 追平（支柱 A）后靠 B3 反超 | 持平/反超（结构化绑定） | CI 环 + 成功路径自评 |
| 质量闭环 | **碾压**（它没做） | **碾压**（它们单次过） | O6 修订环（B1） |
| 图质量 | 反超（它对图盲） | 反超（它们不强制图入正文） | 多模态看图（B2）+ D1 |
| 真实性/可追溯 | 反超（它无校验） | **碾压**（它们给「合理数字」） | 证据绑定 + 一致性（支柱 C） |
| Summary Sheet | 反超（它没有页面级） | **碾压**（它们不会自动出） | D2 |
| 敏感性/校验 | 反超（它只一步 prompt） | 反超 | D3/D4 硬门 |
| 投稿级 PDF | **碾压**（它只出 md） | **碾压**（它们不天然出） | 支柱 F |
| 语言纯度/排版 | 持平/反超 | 持平 | D5 + lint |
| 引用 | 追平（它有 OpenAlex） | 反超 | 接入 OpenAlex/Semantic Scholar |

「碾压」= 对手结构性缺失；「反超」= 对手有但弱；「追平」= 必须先补的对等项。

---

## 5. 分期路线（P0→P4）

> 原则：先用 **P0 快赢**把基线抬到「像样」（也给实验一个体面的 mag-v0）；再上 **P1 求解环**（最大杠杆）；再上 **P2 闭环引擎**（护城河）；P3 多模态/检索；P4 HITL/打磨。每期末跑一次 §7 的 **Proof-Lite** 看涨幅。

| 期 | 内容 | 退出标准（exit criterion） |
|---|---|---|
| **P0 快赢**（支柱 D 全 + C 的 PQ2 + E2 切 pro） | D1–D5、PQ2、默认 pro | MockJudge 由 ~4.7 → **6.5+**；figures≥6；PDF 非零图；Proof-Lite 上 mag-v0 ≥ MMA-默认 在 figures/summary 维 |
| **P1 求解环**（支柱 A 全 + B3） | CI 持久 kernel、单工具 ReAct、分段状态、成功路径自评、沙箱、兜底 | `data_solution`/`mathematics`/`validation` 维显著升；产 `notebook.ipynb`；真题主指标非平凡 |
| **P2 闭环引擎**（支柱 B1 + 支柱 C 全 + 支柱 F） | O6 修订环、证据绑定审计、PDF 硬门 | 低维触发定向 repair 且总分收敛上升；正文未注册数字被拦；编译失败必拦 |
| **P3 多模态/检索**（支柱 B2 + E1 + E3） | 看图自评、per-role 模型、方法/代码 RAG | figures 维超「数字描述」基线；求解环首轮成功率升 |
| **P4 HITL/打磨**（支柱 G + 排版 lint 收尾） | 真六动作 gate、语言/编号 lint 收口 | 你在场验收 UX；端到端稳定 |
| **Proof-Full** | §7 完整实验 | 见 §7 的 W1–W3 |

每期：子代理逐任务（TDD→复审→修→提交），按组 `git push origin main`；**仅提交 src/tests/docs，绝不 `git add -A`**（assets/ 版权永不提交）。

---

## 6. 优先级一览（价值/依赖排序）

1. **P0 全部**（D1 图入正文 = 单项最高性价比；D2 Summary Sheet；D3/D4 硬门；D5 语言；PQ2 摘要一致；切 pro）。
2. **P1 支柱 A**（求解环 = 最大架构杠杆，是「真实数字」的前提）+ B3 成功路径自评。
3. **P2 支柱 B1（O6 闭环）+ 支柱 C（一致性/证据）+ 支柱 F（PDF 硬门）** —— 护城河成型。
4. **P3 B2 看图 + E1/E3 模型与检索**。
5. **P4 支柱 G HITL**（有人时）。

---

## 7. 实验设计：如何**证明** mag 超过其他系统

> 目标：把「我们更强」做成**可证伪、可复现、经得起同行推敲**的数字结论。核心原则：**预注册、双盲、锚定真实 O/M/F 论文、独立评审团（不用我们自己的 MockJudge 当裁判）、配对统计、held-out 不可回灌**。

分两档落地：**Proof-Lite**（开发期每期跑，快速信号）与 **Proof-Full**（里程碑级，对外可发布的证明）。

### 7.1 题库与锚定（benchmark & anchors）
- **题目**：COMAP 2018–2024，覆盖四类（连续/物理=MCM A、离散/优化=MCM B、数据驱动=MCM C〔mag 主战场〕、开放/政策=ICM D/E/F）。
- **拆分**：总 **N=18**。**校准集 6 题**（2018–2020，用于定 rubric、调裁判 prompt、对齐人评、给 mag 开发期迭代——这 6 题视为「已烧毁/可能泄漏」）；**held-out 测试集 12 题**（2021–2024，开发期**永不打开**，跑测前用 git commit hash **封存**）。所有对外夺标结论只用 held-out。
- **锚点**：每题取 3 篇真实获奖论文（Outstanding / Meritorious / Finalist）作为**固定刻度锚**：校准裁判刻度（O>M>F 排序错的裁判淘汰）、提供「与人类差距」分母、每批与 agent 论文一起盲评。来源 COMAP/UMAP Journal；缺 M/F 时用其它年 O 篇作天花板锚并标注不对称。锚点**绝不**喂给任何 agent（泄漏向量）。

### 7.2 评分方法（judging）
- **Rubric 10 维**（与 `mock_judge.py` 的 DIMENSIONS 对齐，便于和 mag 自评对照）：summary_sheet / problem_coverage / modeling / mathematics / data_solution / validation / sensitivity / figures / writing / coherence。每维 0–10，给**锚定分档描述**（0–2 缺失/错、3–4 有但弱、5–6 合格、7–8 强、9–10 O 奖级），在校准集上冻结。总分=维度均值 + **另测一个 0–100 整体「会得奖吗」判断**（与维度分分开，便于发现刷分）。
- **评审团**：**≥3 个来自不同模型家族的前沿 LLM 裁判**（如 GPT 系、Gemini 系、一个非 Anthropic 开源），且 **mag 所用模型家族不得在评审团占多数**；理想再加 **2–3 名人类 MCM 评委/资深教练**对子集（全部锚点 + 随机 20% agent 论文）评分，作为 LLM 团的对齐锚。头条分=与人对齐的 LLM 团均值；人评单列并作校准目标。
- **盲法**：所有论文（含真实锚点）统一 PDF 模板归一化、去身份串（队号/「generated by」/水印/特征页眉）、随机 UUID、乱序、无系统标签。评完做**盲法完整性检查**：让裁判猜哪些是 AI 写的，命中率远超随机 → 盲被破，加强归一化。
- **裁判校准**：校准集上用 LLM 团 + 人评所有锚点；只接受 (a) ≥5/6 题保持 O>M>F 排序、(b) 与人评 Spearman ρ≥0.6 的 LLM 进团；不合格降权/剔除。
- **一致性**：报 Krippendorff α / ICC(2,k)（连续维）+ Fleiss κ（会得奖二元）。目标 ICC≥0.6；不达则在校准集精修维度描述再冻结。

### 7.3 公平对照（fairness）
- **同输入**：每系统拿到逐字节相同的官方题目 PDF + 官方数据 + 相同「投稿须知」（页数、Summary Sheet、格式）。无人给额外提示/锚点/中途指导。
- **同预算**：① 墙钟上限（如 4h，远小于 96h 但全员相等）② 算力/成本上限（token 或 USD）。超限即截断按现状评分。
- **同模型档**：凡可换底座的系统（mag/MMA/Claude Code/Codex）**钉同一前沿模型版本快照**；Hermes 若锁死自有模型，按其原生模型跑并**标注为已知混淆**，另做「mag 用 Hermes 同档」的敏感性分析。记录每次 run 的精确 model id。
- **归一化输出 PDF**：通用 Agent 不天然出竞赛 PDF → 用**与重排锚点论文相同的中性 LaTeX 模板**机械编译其 LaTeX/文本（同一步、不改内容、记 diff）。不能编译 = 该系统真实失败（低分），不人工补救。
- **能干操作者对等**：每个竞品用**预注册、善意撰写**（参考其官方最佳实践、可由中立方审）的固定操作脚本，held-out 前冻结，防止 strawman。通用 Agent 用统一「你是 MCM 队，产出完整论文」harness prompt。
- **环境对等**：同机型、同网络策略（全在线或全离线 + 相同缓存）、run 顺序随机/抵消，记 model id/时间戳。

### 7.4 方差与统计（variance & stats）
- **设计**：在题目上**完全配对/分块**；每个 (系统×题) 跑 **R=5** 次独立 run（不同 seed/session）。held-out 总 run = 5 系统 × 12 题 × 5 = **300 篇** + 36 锚点，每篇 ≥3 裁判。
- **报告**：每维 + 总分 mean ± 95% CI（按题聚类的 bootstrap）；给**完整 10 维画像**（雷达/表），不只总分；给每题胜负矩阵。
- **主检验**：mag vs 每个竞品，按题均分（5run×裁判 → 每题一个数）做 **Wilcoxon 符号秩检验**（配对 t 作确认）；多重比较（4 对 × 2 端点）用 **Holm-Bonferroni** 控 FWER@0.05。
- **效应量**：matched-pairs rank-biserial（Wilcoxon）+ 配对 Cohen's d_z + CI。再用**混合效应模型**（run 嵌套题嵌套系统，裁判作交叉随机效应）分解方差，量化各系统 run-to-run 不稳定度（均值高但方差大 = 对真实参赛者更差）。

### 7.5 防过拟合 / 防刷分（anti-overfit）
- **裁判独立于 mag**：mag 的 `MockJudge` **不得**进评审团，mag 自评所用模型家族不得主导评审团。**两个分都报**：(a) mag 自评对所有论文（含竞品）的分；(b) 独立团的分。若 mag 在自评上赢很多、在独立团上缩水/消失 → **公开**为「自评乐观偏差」。
- **held-out 纪律**：12 题在任何人打开前封存（hash+时间戳）；rubric/裁判只在 6 校准题上调；**不得用 held-out 分迭代 mag**；held-out 一次性终评。改 mag 后要重测 = 换新 held-out。
- **人类抽检**：人评全部锚点 + 随机 20% agent 论文（盲），验证/反驳 LLM 团；人-机分歧作为每条结论的不确定带。
- **泄漏/刷分检查**：(1) 探测各 agent 是否记忆 held-out（与真实锚点的 n-gram/嵌入重叠、是否逐字复现获奖结构）；(2) 因 rubric 半公开，查 mag 是否「关键词堆砌」（写了「敏感性分析」却没真做）——靠人类抽检 + 抽样「论断-证据核实」审计；(3) **预注册**完整分析计划后再解封。

### 7.6 取胜判据（win criteria，预注册、可证伪）
**mag 超越竞品 C** ⇔ 同时满足：
- **W1**：held-out 12 题上，mag 每题均分（**独立团**、维度均值端点）高于 C，Wilcoxon 经 Holm-Bonferroni 后 **p<0.05** 且 rank-biserial≥0.5（或 d_z≥0.5）。
- **W2**：在「会得奖」整体端点上同向取胜（两端点不矛盾）。
- **W3**：结论在**独立团**成立（不只在 mag 自评的 MockJudge 上）。

**「mag 超越全部对手」** = W1–W3 对 MathModelAgent **和** Claude Code、Codex、Hermes **各自**成立。

**与人类差距（更强的次级主张）**：每题 gap-closed = (mag_mean − Finalist锚)/(Outstanding锚 − Finalist锚)，报均值 + CI；可信「竞赛级」设 **≥50%**（mag 论文落在 Finalist 与 Outstanding 之间至少一半）。

**诚实披露**：p≥0.05 或效应<0.5 → 明确报「无显著差异」或「mag 在维度 D 落败」；超越失败处用 TOST 等价检验报「不更差」。

### 7.7 Proof-Lite（开发期每期跑，便宜快）
- 题：2–3 道校准题；系统：mag-当前 vs MMA-默认 vs Claude Code（先三家）；裁判：mag 自评 MockJudge **+ 1 个独立 LLM 家族**裁判；R=2。
- 目的：每期看维度涨幅、抓回归；**不**作对外结论（held-out 不动）。
- 落点：`scripts/score_paper.py` 扩成 `scripts/bench.py`（多系统/多题/多裁判，输出 10 维表 + 配对差）。

### 7.8 实验执行顺序（protocol）
1. **预注册**：写并打 git hash（题单、拆分、10 维 rubric 分档、裁判名册、统计检验、Holm 家族、W1–W3 阈值）——**在打开任何 held-out 前**。
2. **集题与锚**：18 题 + 官方数据 + 每题 O/M/F 真论文；版权私存（见风险）；封存 12 held-out（hash）。
3. **归一锚点**：36 篇重排进中性 LaTeX 模板、去标识、UUID；此模板即全 agent 输出 harness。
4. **建裁判 harness**：≥3 个异家族 LLM 团 + 冻结 rubric prompt；并行记 mag 自评分。
5. **校准**（6 题）：评锚点，验 O>M>F 与 ρ≥0.6，定团，记 ICC。
6. **冻结竞品操作脚本**：善意撰写 + 钉同模型档 + 记 model id。
7. **试点**（仅校准题）：全系统跑 1–2 题验预算/编译/方差，定 R/N。
8. **解封 held-out 并跑**：5×12×5，统一预算、乱序、同机型、记 id/token/时间/编译 diff。
9. **归一+盲**：300 篇编译、去标识、UUID、乱序、混入锚点。
10. **评分**：独立团评全量 10 维 + 整体；人评锚点 + 随机 20%；mag 自评单列；跑盲法完整性检查。
11. **分析**：维度+总分 mean±CI（题聚类 bootstrap）、Wilcoxon+配对 t、效应量、Holm、混合效应方差分解、ICC/κ、gap-to-human。
12. **双裁判对照报告**：独立团作头条，mag 自评并列，分歧标注为自评乐观；裁定 W1–W3，诚实报胜/平/负 + 10 维画像。
13. **稳健性与发布**：留一裁判/留一题重算、Hermes 同档敏感性；公开数据/脚本/操作脚本/rubric/预注册供复现（题目与锚点受版权约束不公开，见风险）。

### 7.9 实验风险与缓解（threats to validity）
| 风险 | 缓解 |
|---|---|
| **数据泄漏/记忆**：held-out 题与名篇可能在训练集里 | 偏好近年（2021–24）；n-gram/嵌入重叠检查；探测逐字复现；按题标泄漏风险，重记忆题作子组不进头条 |
| **裁判偏好**（自家族偏好） | mag 家族不进评审团多数；多家族；锚定人评；留一裁判；盲法 AI 检测 |
| **裁判/rubric 过拟合**（刷我们自己的分） | 独立团 + 改写 rubric；人类「论断-证据」审计；报自评 vs 团 delta；预注册防事后挪标 |
| **竞品 strawman** | 预注册善意操作脚本（按各家最佳实践，中立方审）；公开配置；同输入/预算/模型档；同时报等价检验 |
| **COMAP 版权** | 题目/获奖论文私存仅内部评测，不再发布；按年+题号引用；公开只发派生分数/脚本 |
| **模型档不对称**（Hermes） | 显式标注；做 mag 同档敏感性；两者都报 |
| **端点漂移**（API 版本/负载） | 钉版本快照；run 顺序随机/抵消；记 id/时间戳；run-date 作协变量 |
| **小 N/方差** | 配对 + R=5；题聚类 bootstrap；预注册功效分析，必要时扩到 N=15；报方差分量 |
| **输出 harness 偏置** | harness 纯机械、记每个 diff；不可编译=真失败；抽样审中性 |
| **构念效度**（rubric 高 ≠ 真会获奖） | 锚定真 O/M/F；报 gap-to-human；抽样请资深教练给真实「夺奖概率」判断 |

---

## 8. 总体里程碑与「开发↔证明」交织

```
P0 快赢 ──► Proof-Lite#1（mag-v0 vs MMA vs Claude Code，校准题）
P1 求解环 ──► Proof-Lite#2（看 data_solution/math/validation 涨幅）
P2 闭环引擎 ──► Proof-Lite#3（看 O6 收敛 + 一致性）
P3 多模态/检索 ──► Proof-Lite#4（看 figures 反超）
P4 HITL/打磨 ──► 预注册 + 解封 ──► Proof-Full（W1–W3 终裁）
```

- 每个 Proof-Lite 只用**校准题**，守住 held-out 一次性。
- Proof-Full 是对外可发布的「我们超过了 X」的硬证据，安排在 P4 后、且**预注册先行**。

---

## 9. 风险与诚实边界（开发侧）
| 风险 | 缓解 |
|---|---|
| 支柱 A（求解环）体量大、Jupyter kernel 在子进程/沙箱里不稳 | 拆 3–4 个 TDD 任务；保留现有确定性兜底；kernel 崩溃降级到一次性 codegen |
| pro 模型更贵更慢 | 轻量阶段留 flash（per-role 选模型）；e2e 设预算上限 |
| MockJudge LLM 评分有噪声 | 同记离线启发式；多次取均值；关注**维度相对变化**而非绝对值；Proof 用独立团 |
| O6 闭环可能无限重跑 | `max_judge_iters` 封顶 + 分数不升即停（沿用 `RepeatedGateFailureError` 尽力出稿） |
| 通用 Agent 文笔可能不输我们 | 取胜面压在结构化/可验证/可追溯（支柱 C/D/F），不赌纯文笔 |
| 「超越」可能在某些维度不成立 | 实验诚实分维报；只在个别维 clear W1 才下该维结论；等价检验兜底 |
| 我可能高估 mag、低估对手 | 已用源码审计去夸张（MMA 头条多为未实现）；Proof 用独立裁判 + 人类抽检纠偏 |

---

## 10. 待你拍板的决策点
1. **分期顺序**：是否按 P0 快赢先行（推荐，给实验一个体面基线），还是直接上 P1 求解环（最大杠杆但见效慢）？
2. **实验档位**：先只做 **Proof-Lite**（便宜、内部、每期跑）；**Proof-Full** 是否现在就锁题、预注册、找人类评委（成本高、需真实获奖论文与人力）？
3. **对手范围**：Proof-Full 是否四家全上（MMA + Claude Code + Codex + Hermes），还是先三家（去掉模型档不对称的 Hermes）？
4. **模型预算**：per-role 选模型里，writer 是否也上 pro/或换更强文笔模型？e2e 墙钟/成本上限设多少？
5. **HITL（支柱 G）**：是否纳入主线，还是和 CLI 客户端/服务端一起留到你在场？

---

## 附录 A · 本计划的研究依据（审计原始结论摘要）
- **MMA 架构**：agentless 手写编排，4 agent（coordinator/modeler/coder/writer）线性 + `flows.py` 固定论文骨架；A2A pydantic 契约；Redis pub/sub + WebSocket 进度；输出单一 `res.md`。无 DAG、无并行、无重规划。
- **MMA 求解环**：`coder_agent.py` 单工具 `execute_code` ReAct + 持久 Jupyter/E2B kernel + `.ipynb`；**仅报错时反思**；**对图盲**（图被替换为占位文本）；stdout 截断 ~1000 字符。
- **MMA 容错/HIL/RAG**：四层容错、Evaluator、Feedback Rerun、HIL 六动作、RAG **均未实现**（README 后期计划未勾选 + 代码 TODO/配置桩）；真实只有 retry 计数 + 上下文压缩 + Writer 的 OpenAlex 引用。
- **MMA 论文管线**：Writer 强制图入文 + ≥3 行分析 + 真引用；但**无评分、无一致性校验、无 PDF 编译**（只拼 markdown）。
- **mag 缺口**：求解仍是一次性 codegen；MockJudge/一致性资产**未接成闭环**；图未入正文。
- **评测方法学**：N=18（6 校准 + 12 held-out 封存）、真 O/M/F 锚点、≥3 异家族 LLM 团 + 人评、双盲 + 归一 PDF、配对 Wilcoxon + Holm + 混合效应、ICC/κ、gap-to-human、预注册、W1–W3 取胜判据、双裁判对照防自评乐观。

*（完整审计 JSON 见本会话研究产物。）*
