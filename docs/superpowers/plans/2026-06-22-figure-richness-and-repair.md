# 图丰富 + 图靶向修复 实施计划（补 figures 维）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** 把 figures 维从长期 0–2 拉起来:(FIG1) 概念图渲染成 **PDF**(matplotlib)从而能嵌入正文——这是 `figures=1` 的根因;(FIG2) 增加真实**敏感性数据图**(更多可嵌入图);(FIG3) `figure_planning` 消费 `repair_directive`,figures 维弱时多规划图。

**Architecture:** 复用现有 `FigurePlanningAgent`/`VisualizationAgent`(`src/mcm_agent/agents/visualization.py`)。概念图当前 `output_formats=["svg"]` + `_write_mermaid` 只出 `.mmd/.svg` → writer 只嵌 `.pdf` → 不嵌 → figures=1。环境无 svg→pdf 工具(无 cairosvg/inkscape),但有 matplotlib 3.10 → 用 matplotlib 把 `ConceptDiagramSpec`(nodes/edges)画成 PDF。

**Tech Stack:** matplotlib(已装);现有 FigurePlanItem/FigureRecord/ConceptDiagramSpec;repair_directive(已有)。

## Global Constraints
- **降级 + 不崩**:任何单图渲染失败 → 跳过该图、不崩流水线(沿用 visualization.run 的 per-item try/except)。
- **向后兼容**:无 repair_directive → 行为同现状;现有 768 测试全绿。
- **不伪造**:数据图来自真实 results CSV;概念图来自真实 spec(claim/evidence/source 关系)。
- 仅提交 src/tests/docs;**绝不 git add -A**;提交结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;推 main。
- 测试不起真 LLM;matplotlib 用 Agg(visualization 已设)。

## 文件结构
- 改 `src/mcm_agent/agents/visualization.py`(概念图 PDF 渲染 + output_formats + 敏感性图规划 + FIG3 directive)
- 测试 `tests/test_visualization.py`、`tests/test_figure_embedding.py`(嵌入)、新 `tests/test_figure_repair.py`(FIG3)

---

## Task FIG1: 概念图渲染为 PDF(matplotlib)→ 可嵌入(figures=1 根因)

**Files:** Modify `src/mcm_agent/agents/visualization.py`; Test `tests/test_visualization.py`

**Interfaces — Produces:** 概念图 FigurePlanItem 的 `output_formats` 含 `"pdf"`;新增 `VisualizationAgent._render_concept_pdf(workspace_root, item, spec) -> str`(用 matplotlib 把 spec.nodes 画成竖排带框节点、spec.edges 画成带箭头连线,存 `figures/<id>.pdf`,返回相对路径);`_write_mermaid`(或新 `_render_concept`)在产出 `.mmd/.svg` 的同时产出 `.pdf` 并把 `.pdf` 放进 `FigureRecord.outputs`(放在最前,使 writer `_best_output` 选它)。matplotlib 渲染失败 → 仅退回 svg(不崩)。

- [ ] **Step 1: 失败测试** `test_concept_diagram_outputs_pdf_and_embeds`:构造有概念图的 workspace(沿用现有概念图测试搭建)→ `VisualizationAgent().run` 后 `figures/fig_method_overview.pdf` 存在,且 `figure_registry.json` 中该图 outputs 含 `.pdf`;再跑 writer,断言 `model.tex`(其 target_section)出现 `\includegraphics{...fig_method_overview...}`(沿用 test_figure_embedding 的断言风格)。
- [ ] **Step 2: 跑测确认失败**(当前只 svg、不嵌)
- [ ] **Step 3: 实现** `_render_concept_pdf`(matplotlib:每个 node 一个 `FancyBboxPatch` + 居中 label,按顺序竖排;每条 edge 一个 `annotate` 箭头 + 可选 label;`fig.savefig(pdf, bbox_inches="tight")`);`_concept_diagram_figures` 的 `output_formats=["pdf","svg"]`;概念图渲染分支调用它并把 pdf 加入 outputs(首位)。全程 try/except 降级。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_visualization.py tests/test_figure_embedding.py -q`
- [ ] **Step 5: 提交** `feat: render concept diagrams to PDF (matplotlib) so they embed in the paper [FIG1]`

---

## Task FIG2: 敏感性数据图(更多真实可嵌入图)

**Files:** Modify `src/mcm_agent/agents/visualization.py`; Test `tests/test_visualization.py`

**Interfaces — Produces:** `FigurePlanningAgent.run` 在存在 `results/sensitivity_analysis.csv` 时追加一个 `data_plot` FigurePlanItem(`figure_id="fig_sensitivity"`,`source_data=["results/sensitivity_analysis.csv"]`,`target_section="paper/sections/sensitivity.tex"`,`output_formats=["pdf","svg","png"]`,caption 说明参数扰动 vs 指标)。`_render_data_plot` 已能画任意数值列 → 复用;无该 CSV 或无数值列 → 不规划/跳过(降级)。

- [ ] **Step 1: 失败测试** `test_sensitivity_figure_planned_and_rendered`:workspace 有 `results/sensitivity_analysis.csv`(≥3 行,含数值列)→ 规划含 `fig_sensitivity`;`run` 后 `figures/fig_sensitivity.pdf` 存在且 registry 的 used_in 指向 sensitivity.tex;无该 CSV → 不出现 `fig_sensitivity`(不崩)。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** 规划追加 + 复用 `_render_data_plot`(已对无数值列返回 None 跳过,FIG 已有保护)。
- [ ] **Step 4: 跑测通过 + 回归** `pytest tests/test_visualization.py -q`
- [ ] **Step 5: 提交** `feat: plan+render sensitivity-analysis figure into the paper [FIG2]`

---

## Task FIG3: figure_planning 消费 repair_directive(figures 维靶向)

**Files:** Modify `src/mcm_agent/agents/visualization.py`(FigurePlanningAgent.run); Test `tests/test_figure_repair.py`(新)

**Interfaces — Consumes:** `core/repair_directive.py::read_repair_directive`(已有)。**Produces:** `FigurePlanningAgent.run` 开头读 directive,若 `target_stage=="figure_planning"`(figures 维弱),则:(a) 把 directive 的 critique/suggestions 写进新规划图的 `caption_intent`/`purpose` 作为改进提示;(b) 确保至少规划一张概念图 + 一张敏感性图 + 结果图(即"多出图")——即 figures 弱时**强制更丰富**的图集。无 directive 或不同 target_stage → 现状。

- [ ] **Step 1: 失败测试** `test_figure_planning_consumes_repair_directive`:写 `review/repair_directive.json`(target_stage=figure_planning, weak_dimension=figures, critique="figures too few/weak", suggestions=["add result and sensitivity plots"])→ 规划图数量 > 无 directive 时,且某图 purpose/caption 含 critique 文本;无 directive → 数量同现状。
- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现** run 读 directive + figures 弱时强制追加图集 + 注入提示。
- [ ] **Step 4: 跑测通过 + 全量回归** `pytest -q`(全绿硬门)
- [ ] **Step 5: 提交** `feat: figure_planning consumes repair_directive for targeted figure repair [FIG3]`

---

## Task FIG-V: 真题 e2e 验证(figures 维前后对比)
- [ ] 装真 deepseek-v4-pro 跑 MCM-C 全流水线(含 O6 靶向闭环 + 新图)。
- [ ] 真实-judge `score_consensus` 评分,重点看 **figures 维**(目标 ≥4)与总分较 1.5/0.6 的涨幅;`figure_registry.json` 应有 ≥3 张嵌入 PDF。
- [ ] 记新基线到 memory + `assets/b5_runs/`(不提交 assets)。

## Self-Review
- 覆盖:figures 根因(FIG1 概念图 PDF)+ 更多图(FIG2 敏感性)+ 靶向(FIG3 directive)。
- 降级:每图渲染 try/except;无 CSV/无 directive 均退回现状。
- 类型一致:output_formats 含 "pdf";FigureRecord.outputs 首位 pdf;repair_directive 字段与 A 阶段一致。

## Execution Handoff
Subagent-Driven:FIG1 → FIG2 → FIG3 → FIG-V。都改 visualization.py,顺序串行避免冲突。每组推 main。
