# Mag 真实出稿引擎设计（CLI 成品化 + 真题正确论文）

> 状态：设计草案，待用户复核。
> 日期：2026-06-19
> 目标读者：实施本设计的开发者（含全自动 Agent）。

## 1. 目标与成功标准

把 Mag 从"fake provider 下结构完整、真 provider 下跑不通/内容错误"的状态，推进到两个硬指标：

1. **CLI 成品标准**：用户在赛题文件夹输入 `mag`，能用真实 provider 完成"对话讨论 → 配置 → 锁研究脚本 → 自动建模求解写作 → 产出可编译 PDF 与提交包"，并能循环修订。
2. **真题正确性**：以 **2026 MCM Problem C（Data With The Stars）** 为标准验收题，扮演真实用户走完整流程，产出一篇**内容对题、可编译、语言一致**的论文（不是格式正确但模型跑偏的废稿）。

验收以"对题正确性"为主，不要求拿奖级质量；但论文必须真正回答题目子问题（本题：估计隐藏 fan votes、验证淘汰一致性、对比 rank/percent、分析选手特征、提出更优体系），而非输出通用 EDA/罐头模型结果。

## 2. 现状诊断（2026-06-19 真跑结论）

用真实 DeepSeek（`deepseek-v4-flash`）+ 真实数据，绕过 CLI 直驱 `run_mvp_workflow` 跑 MCM C，结论：

**理解层是真智能**：`problem_understanding.md` 正确拆出 4 个子任务、认出"反推 fan votes"、争议选手、评价指标（Spearman/Kendall/Bootstrap CI）、N/A 与淘汰后置 0 的约束。

**但存在以下阻断缺陷：**

| 编号 | 层级 | 缺陷 | 证据 |
|---|---|---|---|
| A | 管道 | CLI `/start` 永远用不上真 provider | `WorkspaceWorkflowAdapter.run_default_workflow` 调 `run_mvp_workflow` 不传 `providers`/`settings`，`run_mvp_workflow` 一律 fallback 到 `_default_demo_providers()`（空响应 FakeLLM） |
| B | 智能 | 讨论 + 自然语言对话是桩 | `cli_commands/start.py` 用确定性 `build_initial_research_script`；`cli_session._handle_natural_language` 无草稿时回固定话术，未接 LLM |
| C | 智能 | 建模=从 8 个固定 solver 选一个 + 列映射，不会写题目专属模型 | `model_decision.md` 把 DWTS 反推题套成 Entropy-TOPSIS；`results/problem1_results.csv` 仅在原数据后加 `priority_score/priority_rank` 两列；`model_metrics.json` 只有 `numeric_mean=10.18` |
| D | 管道 | 论文装配 bug | 摘要把中文 `problem_understanding.md` 原文倒入；Results 报 `row_count/numeric_mean/top_priority_entity` 等通用 EDA；每条 claim 刷 `\cite{web_001..053}` 全量来源 |
| E | 管道 | 可选 provider 失败崩全流程 | `ComplianceOriginalityAgent` 调 UShallPass humanizer 返回 HTTP 400 未捕获，typesetting 阶段抛异常，PDF/打包未执行 |
| F | 管道 | PDF 编译默认坏 + 中文丢失 | `LatexProvider` 写死 `latexmk`（未安装）；本机有 `tectonic 0.16.9`；tectonic 可编译但 lmroman 无 CJK 字体，中文字符被丢弃 |

**关键定性**：执行 harness（`core/experiment.py::run_experiment` 子进程执行 + 超时 + 产物捕获）已存在；`SolverAgent` 本就是"生成 Python 脚本 → 执行"，问题在于脚本是模板拼接固定 `solver_modules`，而非 LLM 题目专属代码。因此内核改造是"换脚本作者 + 加自修复 + 接证据链"，非"从零造沙箱"。

## 3. 决策记录（已与用户确认）

1. **智能内核** = 会写代码的求解 agent（LLM 生成并执行题目专属 Python），罐头 `solver_modules` 退为 baseline/对照。
2. **语言策略**：讨论阶段 agent **主动询问论文语言**（中/英等）；讨论回复语言**跟随用户语言**（用户中文则中文回复，用户要求英文则英文）；论文为中文时仍允许英文缩写/专有名词；论文语言写入研究脚本与 state，并驱动 LaTeX 导言区与 prompt。
3. **范围**：阶段 1 → 2 → 3 顺序全部完成。
4. **Git**：先把当前 `codex/mag-cli-first-implementation` 分支合并到 `main`，之后每个增量直接 commit + push 到 `main`。

## 4. 总体架构（改造地图）

```
            现状                                   目标
讨论    确定性脚本 + 桩对话              → LLM 真讨论(问语言/方向/口径) → 锁脚本
provider CLI 硬接 fake                   → CLI 解析配置→build_provider_bundle→真跑
求解    模板拼 8 个罐头 solver           → LLM 写题目专属 Python，run_experiment 执行 + 自修复
论文    摘要倒原文/Results=EDA/刷cite    → 真摘要/真结果/收敛引用/语言一致
排版    latexmk(缺)、中文丢             → tectonic + 语言感知导言区(英=lmodern; 中=ctex/xeCJK)
鲁棒    可选 provider 崩全流程           → 可选失败降级、不致命
```

设计不变量：
- 不破坏现有 403 个 fake-provider 测试；新增能力优先写行为测试。
- Agent 间仍通过 workspace artifact 协作，关键产物可审计、可恢复。
- 真实 provider 调用只放在手动/gated 的 smoke，不进默认 CI（避免脆弱与费用）。

## 5. 阶段 1：让真跑端到端不崩（管道）

**目标**：真实 provider 下 MCM C 能从导入跑到可编译 PDF，不崩、不中英混排丢字。

### 5.1 Provider 接线
- 新增配置解析 helper：优先 workspace `.env` + `.mag/config.toml`；缺失项回退仓库根 `mcm_agent_config.local.json`（开发期）。明确优先级与来源日志（不打印 secret）。
- `WorkspaceWorkflowAdapter` 调 `load_settings(...)` + `build_provider_bundle(settings, workspace_root=...)`，把真实 bundle 与 settings 传入 `run_mvp_workflow`。
- `/api`、`/status` 反映真实 provider 状态（已接线后从同一配置源读取）。

### 5.2 可选 provider 降级
- 定义"硬依赖 vs 可选"清单：硬依赖=LLM（讨论/理解/写作/求解 codegen）、LaTeX（出 PDF）、数据读取；可选=humanizer、search/extractor、official_data、embedding/rerank、mineru（非 PDF 题面时）。
- 可选阶段（首要 `compliance`/humanizer，其次 search/extract）包 try/except：失败记 `.mag/logs/` 并跳过/降级，不抛异常中断 workflow。

### 5.3 LaTeX 与语言
- `LatexProvider` 命令探测优先级：`tectonic` → `latexmk` → `xelatex`；tectonic 用 `tectonic main.tex` 语义，不复用 latexmk 参数。
- 语言感知导言区：英文用 lmodern；中文用 ctex/xeCJK（tectonic 默认走 XeTeX，可支持）。论文语言来自研究脚本/state。

### 5.4 论文装配 bug
- 摘要：改为 LLM 生成的真实摘要（基于研究脚本 + 真实结果），不再倒报告原文。
- Results：从真实 solver 结果取数（阶段 2 完成后为题目专属结果；阶段 1 先保证不报通用 EDA 噪声、不刷全量 cite）。
- 引用策略：每条 claim 只引相关来源；移除"全量 53 条 cite"。

**阶段 1 验收**：真跑 MCM C 不崩、产出 `output/draft/main.pdf` 可编译；语言一致无丢字。

## 6. 阶段 2：会写代码的求解 agent（智能内核，重点）

**目标**：论文内容对题——真实题目专属模型与结果，而非罐头模型。

### 6.1 SolverCoderAgent
- 输入：锁定研究脚本（含子问题、模型路线、数据需求、指标）+ 数据 schema profile（已有 `results/schema_profile.json`）+ `problem_understanding.md`。
- LLM 产出题目专属 Python，遵守**代码契约**：
  - 从 `input/data/` 读取数据（路径作为约定/参数注入）。
  - 把结果写到约定路径：`results/*.json`（指标/估计/对比）、`figures/*`（图）、必要的中间 CSV。
  - 只用允许的库（pandas/numpy/scipy/sklearn/matplotlib 等已装依赖）。
- 用现有 `run_experiment(workspace_root, command, produced_files=..., timeout_seconds=settings.code_timeout)` 执行；捕获 stdout/stderr 与产物。

### 6.2 自修复循环
- 执行失败（非零退出 / 缺产物 / 异常）：把 traceback + 失败产物回喂 LLM，请求修复，重试有限次（如 ≤3，可配）。
- 全部失败：降级到罐头 `solver_modules` baseline，并在 `validation_gate` 标记 degraded，写明原因，必要时进入 blocked 让用户介入。

### 6.3 结果接入证据链与论文
- 真实指标 → `evidence_registry.json` → `claim_plan` → 论文 Results/Model 章节。
- 论文写作（writer/paper_sections）改为基于真实结果与研究脚本生成对题文字，语言遵循策略。

### 6.4 validation_gate
- 校验：代码跑通、约定产物存在、结果非平凡（启发式：不是"仅复制输入/仅加常数列"；含题目要求的关键量，如本题的 fan-vote 估计与淘汰一致性度量）。

**阶段 2 验收**：MCM C 真跑产出含 fan-vote 估计、淘汰一致性度量、rank/percent 对比的真实结果，并体现在论文 Results 中。

## 7. 阶段 3：真·对话式 CLI

**目标**：达到"成品 CLI"——用户能在 CLI 真讨论、看进度。

- 讨论循环：`/start`（或自然语言）进入 LLM 多轮讨论；agent **主动询问论文语言**、确认研究方向/数据口径/子问题边界；从对话构建研究脚本草稿，用户迭代；`/start --lock` 锁定（写入语言与方向）。
- 自然语言路径接 LLM，带 workspace 上下文（题面、state、RAG top-k）；讨论语言跟随用户语言。
- 运行进度：workflow 执行时显示人类可读阶段（正在理解题目/检查数据/写代码求解/画图/写论文/审查/打包），底层 stage/gate 仍可 `mag inspect`。
- 修订循环：复用现有 `revision_plan`，确认后局部重跑。

**阶段 3 验收**：用户能在 CLI 用中文讨论、被询问论文语言、看到进度，全程不需手改文件。

## 8. 测试与同步策略（横切）

- fake-provider 单测保持全绿；每个增量新增对应行为测试。
- 新增真 provider smoke 脚本（如 `scripts/real_smoke.py`，读 `mcm_agent_config.local.json`，跑精简 MCM C），手动运行、默认不进 CI。
- 每个增量：`pytest -q` + `ruff check src tests` 绿 → commit → push `main`。
- 每阶段末用 MCM C 做一次真跑回归，记录朝"正确论文"的逼近。
- MCM C 题面/数据为 COMAP 版权材料，置于未跟踪的 `assets/`（或 gitignore），不提交进库。

## 9. 风险

| 风险 | 应对 |
|---|---|
| LLM 生成代码不稳定/不安全 | 代码契约 + 受限库 + 子进程超时 + 自修复有限重试 + baseline 兜底 |
| 真 provider 测试脆弱/费用 | 单测全 fake；真 smoke 手动 gated |
| 中文论文排版 | tectonic+XeTeX+ctex/xeCJK；CI 不强依赖本地 TeX |
| 直推 main 风险 | 合并前后保持测试绿；每增量小步可回滚（workspace 之外用仓库 git 历史） |
| 范围过大 | 严格阶段化，每阶段独立验收与提交 |

## 10. 文件影响（预估，details 留给 implementation-plan）

- 改：`core/workflow_adapter.py`、`cli_commands/start.py`、`cli_session.py`、`config.py`、`providers/latex.py`、`providers/factory.py`、`workflows/mvp.py`、`agents/{compliance,writer,paper_sections,solver,validation,discussion}.py`、`agents/reference_manager.py`（引用收敛）。
- 增：`agents/solver_coder.py`（或重构 `solver.py`）、配置解析 helper、`scripts/real_smoke.py`、对应测试。
- 文档：完成后同步 `docs/` 与 `design.md` 的实现状态。
