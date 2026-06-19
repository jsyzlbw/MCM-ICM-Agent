# ADR 0002：采用 `.mag` + `input` + `knowledge` + `work` + `output` 的 workspace 结构

## 状态

Proposed

## 背景

早期 workspace 结构直接暴露许多 workflow 内部目录，例如 `reports`、`data`、`paper`、
`review`。这些目录对开发者清楚，但对普通用户不够友好。

CLI-first 产品需要更清晰地区分：

- 用户导入的文件。
- 用户导入的知识。
- Agent 中间工作。
- 用户最终输出。
- Mag 内部状态。

## 决策

新 workspace 采用：

```text
.mag/
input/
knowledge/
work/
output/
```

含义：

- `.mag/`：Mag 内部状态。
- `input/`：用户给 Mag 的资料。
- `knowledge/`：长期或任务内 RAG 资料。
- `work/`：Agent 可审计中间产物。
- `output/`：用户最终查看的产物。

## 影响

正面：

- 用户更容易理解。
- 中间产物和最终产物分离。
- 对话历史和配置有统一位置。
- 方便未来导出 bug report。

代价：

- 需要从当前 workspace 结构迁移或映射。
- 现有测试和文档需要逐步更新。

## 后续

- 先在 CLI-first 新流程使用新结构。
- 兼容旧 workspace 或提供迁移工具。
- workflow engine 内部可以继续使用现有 artifact contract，但输出映射到 `work/`。

