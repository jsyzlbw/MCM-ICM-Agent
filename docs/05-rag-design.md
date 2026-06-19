# 05. RAG 设计

## 1. 目标

RAG 的目标是让 Mag 学习用户导入的优秀论文、方法笔记、规则说明和案例，而不是让 Agent 凭空
发挥。RAG 提供方法论和写作结构参考，但不能自动成为外部事实来源。

## 2. 用户入口

用户通过 `/rag` 导入文件：

```text
> /rag
Paste one or more file paths.
Type done when finished.
```

支持：

- `.pdf`
- `.md`
- `.txt`
- `.docx`

## 3. 文件组织

导入后复制到：

```text
knowledge/
  papers/
  methods/
  rules/
  cases/
```

Mag 可以自动猜测类型，也允许用户修正：

```text
Detected: paper
Use as:
  1. excellent paper
  2. method note
  3. contest rule
  4. case study
```

## 4. Metadata

每个 RAG 文档需要 metadata：

```json
{
  "document_id": "rag_001",
  "title": "MCM 2024 O Prize Paper",
  "workspace_path": "knowledge/papers/mcm_2024_o.pdf",
  "type": "paper",
  "usage": "methodology_guidance",
  "indexed": true,
  "created_at": "..."
}
```

## 5. Usage Boundary

RAG 文档用途分级：

| usage | 含义 |
|---|---|
| `methodology_guidance` | 可用于建模思路、方法套路。 |
| `writing_pattern` | 可用于论文结构、语言风格。 |
| `contest_rule` | 可用于格式和规则约束。 |
| `review_checklist` | 可用于审查标准。 |
| `source_candidate` | 只能作为候选来源，必须验证后才能引用。 |

默认情况下，RAG 不等于可引用事实来源。

## 6. 检索流程

```text
导入文档
  -> 文本抽取
  -> chunk
  -> metadata
  -> FTS index
  -> vector index
  -> rerank
  -> methodology hits
```

如果 embedding provider 不可用，应退化为关键词检索。

## 7. 在 workflow 中的用途

RAG 参与：

- 题意理解时参考类似题型。
- 建模候选时参考方法库。
- 写作时参考优秀论文结构。
- 图表设计时参考表达方式。
- 审稿时参考 checklist。

RAG 不应该：

- 直接复制论文句子。
- 直接编造引用。
- 用未验证的事实支撑论文 claim。

## 8. 与数据可得性检查的关系

如果 RAG 文档提到某个数据源，Mag 可以把它作为 source candidate：

```text
RAG mentions: NOAA Climate Data Online
Action: verify whether the data is accessible for this problem.
```

只有 source verifier 通过后，才能进入 source registry。

