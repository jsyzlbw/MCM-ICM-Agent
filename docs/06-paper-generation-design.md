# 06. 论文生成设计

## 1. 目标

Mag 生成论文前，必须先有明确研究脚本、数据来源、模型结果、证据和图表计划。论文生成不是
“让 LLM 直接写一篇”，而是基于可审计 artifacts 的写作流程。

## 2. 研究脚本

研究脚本是论文生成的前置条件。

必须包含：

- 题目理解。
- 子问题拆解。
- 研究目标。
- 模型路线。
- 数据需求。
- 数据可得性。
- 指标体系。
- 求解步骤。
- 图表计划。
- 论文结构。
- 风险和替代方案。

保存：

```text
work/discussion/research_script.md
work/discussion/research_script.json
work/discussion/locked_research_script.md
work/discussion/locked_research_script.json
```

## 3. 数据可得性检查

锁定脚本前必须检查数据：

1. 用户上传数据。
2. 题目附件。
3. RAG 中提到的数据来源。
4. 公开搜索。
5. 学术论文。
6. 官方数据库。
7. 需要申请权限的数据库。

结果分为：

- available
- available_with_api
- user_upload_required
- proxy_needed
- unavailable

## 4. 建模与求解

建模阶段输出：

```text
work/reports/model_candidates.md
work/reports/model_decision.md
work/reports/experiment_spec.json
```

求解阶段输出：

```text
work/results/model_route_summary.json
work/results/evidence_registry.json
work/results/experiment_runs.jsonl
```

所有关键数字必须进入 evidence registry。

## 5. 图表生成

图表阶段输出：

```text
work/figures/figure_plan.json
work/figures/figure_registry.json
work/figures/source/
```

图表要求：

- 优先 SVG/PDF vector output。
- caption 与 claim 绑定。
- source data 可追溯。
- 图表应服务论文论证，不做装饰。

## 6. Claim Plan

写论文前生成 claim plan：

```json
{
  "claim_id": "claim_result_001",
  "section": "paper/sections/results.tex",
  "claim_text": "The optimized allocation reduces total cost by 12%.",
  "evidence_ids": ["ev_cost_reduction"],
  "figure_ids": ["fig_cost_comparison"],
  "priority": "critical"
}
```

Critical claim 必须有 evidence、figure 或 source。

## 7. LaTeX 写作

写作阶段：

1. 根据 claim plan 写 section。
2. 在 LaTeX 中保留 trace comment。
3. 只引用 source registry 中通过验证的来源。
4. 不写 unsupported claim。
5. 不保留 unresolved placeholder 到最终提交包。

## 8. 排版与审查

排版阶段：

- 生成 `main.tex`。
- 生成 `references.bib`。
- 编译 PDF。
- 检查图片、表格、公式、引用。
- 做一轮保守修复。

审查阶段：

- 检查证据覆盖。
- 检查图表可读性。
- 检查论文结构。
- 检查最终 blocker。

## 9. 输出给用户

用户主要看：

```text
output/draft/main.pdf
output/draft/reviewer_report.md
output/final/main.pdf
output/package/submission_package.zip
```

复杂中间文件留在 `work/`，供调试和审计。

