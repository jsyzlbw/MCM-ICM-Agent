# B5 真实 e2e 验证：结论与下一步杠杆（deepseek-v4-pro）

- 日期：2026-06-21 / 22
- 用途：把「P1 + 修复 + O6」在 **2026 MCM-C「Data With The Stars」真题**上用真实 deepseek-v4-pro 跑通后的**诚实结论**固化下来（之前散落在对话/ledger/memory）。
- 量尺：`MockJudge` 真实 LLM 评审（deepseek-v4-pro，10 维，0–10）。**注意**：`scripts/score_paper.py <ws>` 用 workspace 设置 → 退化成 `FakeLLMProvider` → 只给离线启发式分（~6.x，偏乐观）。要拿**真实 LLM 评审分**必须：`load_settings(config_file="mcm_agent_config.local.json")` → `build_provider_bundle` → `MockJudge(bundle.llm).score(*read_paper(ws))`。

---

## 1. 一句话结论

**堵点全修好、流水线跑通、框架对题、自评引擎装好——但真实评审分没达到 4.7 历史基线（最好 ~2.4）。** 这一晚最有价值的产出不是分数，而是**用真跑精确定位了真正的瓶颈链**：瓶颈从来不是求解器，而是下游的「盲重跑 + 写作空泛 + 图少 + 评委噪声」。

---

## 2. 真实评审分轨迹（7 次 e2e）

| Run | 含的修复 | 工作流 | 真实 LLM 评审 |
|---|---|---|---|
| 1 | P1 | 完成 | **0.8**（代理框架、模型段空洞） |
| 3 | P1+B6 | 完成 | **0.2**（代理框架、空洞） |
| 4 | +data_feasibility | 卡 source_verifier | —（无稿） |
| 5 | +source_verifier | **富模型**(参与度回归+基尼公平+34季+配对优化)，崩在 visualization | —（无稿） |
| 6 | +visualization 降级 | **完成、DWTS 对题** | **1.5**（但求解退化成浅层 TOPSIS 兜底） |
| 7 (O6) | +O6 自评闭环 | 完成，循环 3 轮 | **0.6**（独立复评；环内 iter 轨迹 1.7→2.4→1.1） |
| 基线 | flash，**中文** | — | **4.7** |

离线启发式始终给 ~6.4–6.8（它只数结构/文件，看不出「论文写错对象/空泛」，**不可信**）。

---

## 3. 瓶颈链（每一层都用真跑验证过）

1. **不是求解器**：run5 证明 deepseek-v4-pro 能写出竞赛级模型（参与度回归 + 基尼系数公平性 + 34 季 + 配对优化）。建模脑子是强的。
2. **盲重跑 ≠ 靶向修**：O6 捕获了评委的 `revision_suggestions`，但重跑修复阶段时**没把这些批评喂进 prompt** → 重跑等于重新抽一次 → 噪声大、非单调（1.7→2.4→1.1）。**这是 O6 当前最大的待补点。**
3. **写作器内容空泛**：即使框架对题，正文仍泛泛（writing/coverage/modeling/coherence 的总开关）。
4. **figures=1**：概念图渲染成 `.svg` 但没嵌入正文（O4 老缺口）。
5. **求解路径不稳**：interpreter 环时而出富模型(run5)、时而退化成 TOPSIS 兜底(run6)。
6. **评委本身有噪声**：同一篇 ±0.5（run7 环内 1.1 vs 独立复评 0.6）→ 单次打分做路由不可靠。

---

## 4. 本会话已交付到 main（origin/main `a958398`，742 测试绿）

按提交顺序：

| commit | 内容 |
|---|---|
| `ac00344` | P1 实施计划文档 |
| `dc0f3e3` | PQ4：LLM 求解路径补确定性敏感性兜底 |
| `d079af3`→`8be75a8` | **P1 有状态 Code-Interpreter ReAct 求解环**（B1/B1b/B2/B3，含 JupyterCodeInterpreter） |
| `6a62e44`/`25cd86a` | run() 降级链 + 删掉伪造运行记录（复审抓出的 Critical） |
| `ec2b394` | **B6**：求解环把代码落 `code/experiments/problem1.py`（救回 refine_from_code 一致性链）+ 禁占位指标 |
| `0fe7369`/`95d06ca` | **data_feasibility** 不再误判自带数据「不可得」；source_verifier 对自带数据豁免 |
| `f9c6b5e` | **visualization** 遇不可画的源降级而非崩溃 |
| `1018757`/`4e3e065` | **O6 MockJudge 自评闭环**（终止性已证明）+ 修 resume NameError |
| `a958398` | **O6 keep-best**：保留最佳迭代而非最后一次 |

战略与计划文档：
- 战略 + 证明实验设计：`docs/superpowers/specs/2026-06-21-surpass-mathmodelagent-and-generalists.md`
- P1 实施计划：`docs/superpowers/plans/2026-06-21-p1-code-interpreter-solver.md`
- 本结论：`docs/superpowers/specs/2026-06-21-b5-findings-and-next-levers.md`（本文件）

> 注：另有并发会话在 main 上做 corpus/RAG 知识库（`src/mcm_agent/corpus/`，计划 `2026-06-21-mcm-corpus-rag-kb.md`）——非本工作流产出。

---

## 5. 下一步杠杆（按性价比排序）

1. **靶向修复（最高杠杆，O6 的自然补完）**：重跑修复阶段时，把评委对弱维的具体批评（`revision_suggestions` + 弱维名 + 当前分）**注入该阶段 prompt**，让它针对性修这条弱点，而不是盲抽。直接打中瓶颈 #2，且 `revision_suggestions` 已捕获，只差接线。
2. **写作器实质化**：让写作器把真实 ModelSpec/指标写成有质内容（瓶颈 #3，writing/coverage/modeling/coherence 总开关）。
3. **评委去噪**：自评打分取 N 次平均或小评审团，让路由稳定（瓶颈 #6）。
4. **图丰富（O4）**：概念图转 PDF 嵌入 + 多出几张目的明确的图（瓶颈 #4）。
5. **求解路径稳定**：诊断 interpreter 环为何时而退化成兜底，让富模型稳定胜出（瓶颈 #5）。

这些正是 MMA（无任何闭环/评分）和通用 Agent（一次过出薄稿）都没有的——**护城河方向对，质量工程在前半程。**

---

## 6. 真题产物（版权材料，存 gitignored `assets/`，不提交）

7 次 e2e 的 PDF + 评分历史拷贝到 `assets/b5_runs/`（见该目录 README）。`/tmp/mag_*` 是临时目录，重启可能丢。
