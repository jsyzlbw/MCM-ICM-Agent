# 贡献指南

## 1. 参与前先读什么

推荐顺序：

1. `README.zh-CN.md`
2. `design.md`
3. `docs/00-overview.md`
4. 与你要改的模块相关的 `docs/*.md`
5. `docs/dev/module-map.md`
6. 对应测试文件

## 2. 开发环境

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check src tests
```

如果这两条命令不能通过，先不要开始功能开发。

## 3. 提交一个改动的建议流程

1. 明确要解决的问题。
2. 找到对应设计文档。
3. 如果设计文档没有覆盖，先补设计。
4. 写测试。
5. 运行测试确认失败。
6. 实现最小代码。
7. 运行相关测试。
8. 更新文档。
9. 运行全量测试和 ruff。

## 4. 代码风格

- Python 目标版本遵循 `pyproject.toml`。
- 使用 Pydantic model 表达结构化数据。
- 文件读写优先用项目内已有 JSON/JSONL 工具。
- 不把 secret 写日志。
- 不让默认测试依赖真实 API。
- 不在 Agent 间传隐藏内存，优先通过 workspace artifact。

## 5. 新增 Agent 的要求

新增 Agent 必须说明：

- 输入 artifact。
- 输出 artifact。
- 失败条件。
- 是否需要 gate。
- 对应测试。
- 对应文档。

## 6. 新增 Provider 的要求

新增 provider 必须有：

- fake 或 skip 模式。
- smoke test。
- 配置字段。
- 脱敏错误。
- 文档说明。

## 7. 新增 Slash Command 的要求

新增 slash command 必须说明：

- 用户输入格式。
- 是否需要 LLM。
- 是否修改 workspace。
- 修改哪些文件。
- 中途取消行为。
- 错误提示。
- 测试。

## 8. 文档要求

所有核心改动都要同步文档：

- 产品行为改动：更新 `design.md` 或 `docs/01-cli-product-design.md`。
- workspace 改动：更新 `docs/02-workspace-design.md`。
- workflow 改动：更新 `docs/03-agent-workflow-design.md`。
- provider 改动：更新 `docs/04-provider-design.md`。
- RAG 改动：更新 `docs/05-rag-design.md`。
- 论文生成改动：更新 `docs/06-paper-generation-design.md`。
- 修订流程改动：更新 `docs/07-review-and-revision-design.md`。

## 9. 不建议的改动

- 在没有测试的情况下重构核心 workflow。
- 让默认流程依赖真实 API。
- 让 LLM 输出成为唯一状态来源。
- 在论文中写没有 evidence 的关键结论。
- 把 RAG 文档默认当作事实来源。
- 在普通用户入口暴露大量开发者参数。

