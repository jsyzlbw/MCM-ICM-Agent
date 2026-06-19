# Mag 文档索引

本目录保存 Mag 的中文设计文档和开发者文档。当前阶段以中文为准，英文版以后再补。

## 产品与系统设计

| 文档 | 内容 |
|---|---|
| [../design.md](../design.md) | Mag 总设计文档，描述最终产品形态和完整用户旅程。 |
| [00-overview.md](00-overview.md) | 项目总览、核心概念、当前实现状态和文档地图。 |
| [01-cli-product-design.md](01-cli-product-design.md) | CLI-first 产品形态、裸 `mag`、slash commands 和启动流程。 |
| [02-workspace-design.md](02-workspace-design.md) | workspace 目录结构、状态文件、输入、知识库、中间产物和输出。 |
| [03-agent-workflow-design.md](03-agent-workflow-design.md) | Agent 阶段、gate、repair flow 和用户参与点。 |
| [04-provider-design.md](04-provider-design.md) | API 分类、最少但必要原则、provider 配置、smoke 和失败策略。 |
| [05-rag-design.md](05-rag-design.md) | RAG 文档导入、metadata、usage boundary、检索流程和事实边界。 |
| [06-paper-generation-design.md](06-paper-generation-design.md) | 研究脚本、数据可得性、建模求解、图表、claim plan 和论文生成。 |
| [07-review-and-revision-design.md](07-review-and-revision-design.md) | 用户反馈、修订脚本、局部重跑、版本记录和 blocker 处理。 |

## 开发者文档

| 文档 | 内容 |
|---|---|
| [dev/architecture.md](dev/architecture.md) | 代码架构分层：CLI、workflow、agents、core、providers、solver、server。 |
| [dev/module-map.md](dev/module-map.md) | 逐模块地图，说明每个目录和关键文件负责什么。 |
| [dev/testing-guide.md](dev/testing-guide.md) | 测试命令、CLI 测试、workspace 测试、provider 测试和文档测试。 |
| [dev/contribution-guide.md](dev/contribution-guide.md) | 贡献流程、代码风格、新增 Agent/Provider/Slash Command 的要求。 |
| [dev/roadmap.md](dev/roadmap.md) | CLI-first 产品化路线图。 |
| [dev/implementation-plan.md](dev/implementation-plan.md) | 从当前设计文档到完整实现的具体任务计划。 |

## 架构决策记录

| ADR | 内容 |
|---|---|
| [dev/adr/0001-cli-first.md](dev/adr/0001-cli-first.md) | 决定采用 CLI-first 产品形态。 |
| [dev/adr/0002-workspace-layout.md](dev/adr/0002-workspace-layout.md) | 决定采用 `.mag` + `input` + `knowledge` + `work` + `output` 的 workspace 结构。 |
| [dev/adr/0003-minimal-api-policy.md](dev/adr/0003-minimal-api-policy.md) | 决定采用最少但必要的 API 配置策略。 |
| [dev/adr/0004-git-safety-net.md](dev/adr/0004-git-safety-net.md) | 决定 workspace 默认启用本地 Git checkpoint，GitHub push 可选。 |

## 推荐阅读路线

新用户：

```text
README.zh-CN.md -> design.md -> docs/00-overview.md -> docs/01-cli-product-design.md
```

新开发者：

```text
README.zh-CN.md
  -> design.md
  -> docs/00-overview.md
  -> docs/dev/architecture.md
  -> docs/dev/module-map.md
  -> 与任务相关的专题设计文档
```
