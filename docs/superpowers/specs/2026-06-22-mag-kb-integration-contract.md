# mag ↔ 语料/RAG 知识库 集成接口契约

- 日期：2026-06-22
- 目的：mag 论文引擎与并发会话在建的 corpus/RAG 知识库（真实 O/M/F 获奖论文）之间的**接口契约**，让两个工作流复利、互不阻塞。北极星：冲 O 奖。
- 两边都读这份；任一边改动契约面需在此更新并知会对方。

---

## 0. 总原则

1. **可选 + 优雅降级（硬约束）**：mag 对 KB 的每一处消费都必须 `kb 不存在 / 检索返回 [] → 照常跑、不报错`。两个工作流任何一边没就绪都不能阻塞另一边。
2. **KB 提供「能力」，mag 决定「在哪用」**：KB 暴露稳定检索 API；mag 在特定阶段调用并注入 prompt。
3. **测量也靠 KB**：真实 O/M/F 论文是评委校准的锚点（见 §4）。这是判断"是否真在往 O 靠"的唯一可信办法。

---

## 1. KB 必须保持稳定的 API 面（KB 会话负责）

mag 依赖以下现有接口（`src/mcm_agent/corpus/`），请保持签名与字段稳定：

```python
# corpus/retrieve.py
section_exemplars(kb_dir, query, *, section, embedding_provider,
                  reranker=None, problem_type=None, top_k=5) -> list[CorpusHit]
methods_for_problem_type(kb_dir, problem_type, *, embedding_provider,
                         reranker=None, top_k=8) -> list[CorpusHit]
# corpus/ingest.py
class CorpusHit(BaseModel): content: str; metadata: dict; rerank_score: float
class CorpusKB:  query(query, embedding_provider, reranker=None, *, where=None, top_k=5, candidate_n=20) -> list[CorpusHit]
# corpus/taxonomy.py
problem_type(year: int, letter: str) -> str
```

- **CorpusHit.metadata 键**（mag 会读取，请勿改名）：`paper_id, year, contest, problem, problem_type, section_type, award, source, chunk_index`。
- **section_type 取值**（来自 `sections._SECTION_RULES` 的分类；mag 按这些值检索）：当前含 `model / results / summary / ...（其余见 _SECTION_RULES）/ other`。
  - **请求 KB 会话**：在本契约 §3 的「mag→KB section 映射」里**确认/补全**这张表，确保至少覆盖 `summary, model, results, sensitivity, assumptions, introduction, conclusion`。若某 section_type 不存在，mag 用最接近的 + `other` 兜底。
- **problem_type 取值**（taxonomy）：`continuous, discrete, data, operations_research, sustainability, policy`（2016+）、`interdisciplinary`（早期）、`unknown`。
- **kb_dir 解析**：mag 用 `settings.corpus_kb_dir`（config 默认 `"corpus_kb"`）。**请求 KB 会话确认** `mag kb build` 是否落在该目录；如不同，统一到 `settings.corpus_kb_dir`。
- **providers**：检索需 `embedding_provider`（`.embed([str])->[vector]`）与可选 `reranker`（`.rerank(query, [str], top_k)`）。mag 从 `ProviderBundle.embedding / .reranker` 传入。
  - **依赖告警**：本地 config 当前 `embedding.provider=fake` → 检索是假的。**真实范例检索需要真实 embedding**（voyage/bge）。冲 O 必须配真 embedding + reranker。

---

## 2. problem_type 解析（mag 负责）

mag 必须把"当前题目"映射到一个 problem_type 来 scope 检索：
- 已知 COMAP 题（有 year+letter）→ `taxonomy.problem_type(year, letter)`。
- 未知/任意题 → LLM 分类器：把题意摘要 + taxonomy 的类型词表喂给 LLM，选最接近的一个 problem_type（落 `reports/problem_type.json`，带置信度）。
- 解析不出 → `None`（检索退化为不 scope problem_type，仍按 section 检索）。

---

## 3. mag 的消费点（mag 负责；每处都可选 + 降级）

| mag 阶段 | 调用 | 注入到哪 | 目的 / 命中的 rubric 维 |
|---|---|---|---|
| `methodology_rag` / `modeling_council` | `methods_for_problem_type(problem_type)` | 建模器 prompt 加「同类获奖论文的方法范例」 | 降幻觉、提模型创意 → modeling/mathematics |
| `paper_writer`（逐 section） | `section_exemplars(query=<本节意图>, section=<本节>, problem_type=)` | 写作器该节 prompt 加 1–3 条范例段作为**结构/深度/文风**参照（不抄，仅模仿组织与详尽度） | **最大杠杆** → summary_sheet/problem_coverage/modeling/writing/coherence |
| `summary_sheet` | `section_exemplars(section="summary")` | 摘要页 prompt 加 O 奖摘要范例 | summary_sheet |
| `mock_judge_gate`（O6）/ 评委校准 | 真实 O/M/F 论文作锚点（见 §4） | 校准评委、稳定路由 | 测量可信度 |

**mag→KB section 映射**（待 KB 会话用真实 section_type 确认）：
`abstract.tex→summary` · `introduction.tex→introduction|other` · `model.tex→model` · `results.tex→results` · `sensitivity.tex→sensitivity` · `assumptions.tex→assumptions` · `conclusion.tex→conclusion` · `summary_sheet.tex→summary`。

**注入纪律（防抄袭/防泄漏）**：范例仅作"结构与深度"参照，prompt 必须明确"模仿组织方式与详尽程度，不得复制句子/数字/具体内容；本题内容必须原创且来自本题真实求解"。范例论文是版权材料，只在本地用，不进任何提交产物。

---

## 4. 评委校准（用 KB 做可信测量）

- 把 KB 里每题的真实 O/M/F 论文转成纯文本，用 mag 的 MockJudge 评分。
- **裁判可信判据**：在校准题上必须能排出 `O > M > F`；排不出的评委/prompt 不可信，需修。
- O6 路由用的分 = 多次评委调用取均值（去噪，见 findings 文档瓶颈 #6）。
- 这是判断 mag 是否真在向 O 靠的锚（呼应战略文档的证明实验 §7）。

---

## 5. 落地顺序（两会话并行，不互相阻塞）

- **mag 侧现在就能做（不依赖 KB）**：targeted-repair（把评委批评喂回重跑）+ writer-depth（提纲→实质草稿→自修订）。在写作器/建模器里**预留 KB 范例注入的 seam**（一个 `exemplars: list[str]` 入参，默认空）。
- **KB 侧就绪后（按本契约）**：mag 把 seam 接到 `section_exemplars`/`methods_for_problem_type`，真 embedding 上线，评委锚点校准。
- 任一边未就绪：mag 的 seam 传空 → 行为等同于不接 KB（降级）。

---

## 6. 给 KB 会话的明确请求（请回话/在本文件回填）
1. 确认 `mag kb build` 的输出目录 = `settings.corpus_kb_dir`（"corpus_kb"）？若否，统一。
2. 回填 `_SECTION_RULES` 的完整 section_type 词表，确认 §3 的映射可行（尤其 summary/sensitivity/assumptions 是否存在）。
3. KB 是否已含/计划含真实 **O/M/F** 三档论文（§4 校准需要 F 与 M，不只 O）？award 字段取值？
4. 检索的 graceful 行为：KB 缺失时 `CorpusKB(kb_dir).query(...)` 是返回 [] 还是抛错？mag 需要"返回 []"（或 mag 自己 try/except 包裹——确认由谁负责）。
5. 真实 embedding/reranker provider 的推荐配置（voyage? bge-m3 + bge-reranker-v2-m3?）。
