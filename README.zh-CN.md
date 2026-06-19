# Mag：命令行数学建模 Agent

Mag 是一个面向 MCM/ICM 数学建模论文的本地命令行 Agent。用户安装后，在赛题文件夹中输入：

```bash
mag
```

即可进入类似 Claude Code / Codex CLI 的交互界面：可以用自然语言与 Agent 讨论，也可以用
`/api`、`/rag`、`/question`、`/data`、`/layout`、`/init`、`/start` 等命令导入资料、
配置 API、启动建模、生成论文并循环修改。

## 当前产品愿景

```text
GitHub 一键安装 mag
  -> 新建赛题文件夹
  -> 运行 mag
  -> 自动初始化 workspace
  -> 自动创建本地 Git 安全网
  -> 配置最少必要 API
  -> 导入题目、数据、模板、RAG 文档
  -> 与 Agent 讨论研究方向
  -> 检查数据是否可获得
  -> 锁定最终研究脚本
  -> 自动建模、求解、画图、写作、排版、审查
  -> 用户反馈修改
  -> 循环修订直到提交包可用
```

Mag 的第一身份是“命令行工具”，不是“Python 包”。Python 只是当前实现和分发方式。

## 一键安装

从 GitHub 安装：

```bash
curl -fsSL https://raw.githubusercontent.com/jsyzlbw/MCM-ICM-Agent/main/install.sh | bash
```

安装完成后验证：

```bash
mag -v
```

然后进入赛题目录：

```bash
mkdir 2026-mcm-c
cd 2026-mcm-c
mag
```

## 文档阅读路线

如果你是第一次了解项目，按这个顺序阅读：

1. [总设计文档](design.md)：理解 Mag 的目标产品形态和完整用户旅程。
2. [项目总览](docs/00-overview.md)：理解系统边界、核心概念和当前实现状态。
3. [CLI 产品设计](docs/01-cli-product-design.md)：理解 `mag` 启动界面和 slash commands。
4. [Workspace 设计](docs/02-workspace-design.md)：理解文件夹结构、状态文件和 artifact contract。
5. [Agent 工作流设计](docs/03-agent-workflow-design.md)：理解多 Agent 阶段、gate 和修复路由。
6. [Provider 与 API 设计](docs/04-provider-design.md)：理解 API 配置、最少必要原则和延迟配置。
7. [RAG 设计](docs/05-rag-design.md)：理解知识库导入、索引、使用边界。
8. [论文生成设计](docs/06-paper-generation-design.md)：理解研究脚本、建模、求解、图表和论文写作。
9. [审查与修订设计](docs/07-review-and-revision-design.md)：理解用户反馈、修订脚本和循环改稿。

如果你想参与开发，继续阅读：

1. [开发者架构说明](docs/dev/architecture.md)
2. [模块地图](docs/dev/module-map.md)
3. [测试指南](docs/dev/testing-guide.md)
4. [贡献指南](docs/dev/contribution-guide.md)
5. [开发路线图](docs/dev/roadmap.md)
6. [完整实施计划](docs/dev/implementation-plan.md)
7. [架构决策记录](docs/dev/adr/0001-cli-first.md)

## 当前仓库已经具备的能力

当前代码已经实现了许多底层能力：

- Typer CLI 入口和 `mag` 命令。
- workspace 初始化和状态文件。
- workspace 本地 Git checkpoint 安全网。
- graph-aware stage executor。
- 多 Agent workflow。
- gate decision 和 repair route。
- provider abstraction。
- fake/demo provider 端到端测试。
- RAG v2：FTS + vector + rerank。
- 数据可行性检查。
- modeling council / model judge。
- deterministic solver modules。
- evidence registry。
- figure planning 和 vector-first visualization。
- LaTeX paper writer。
- paper evidence binding。
- review gate 和 submission packager。

新的设计文档系统的目标，是把这些底层能力整理成一个外部开发者能理解、能参与、能扩展的项目结构。

## 快速开发验证

安装开发环境：

```bash
python -m pip install -e ".[dev]"
```

查看版本：

```bash
mag -v
```

运行测试：

```bash
pytest -q
ruff check src tests
```

运行 demo：

```bash
python scripts/run_demo_task.py --workspace .demo_workspace --clean
mag inspect .demo_workspace
```

运行 CLI-first smoke：

```bash
python scripts/run_cli_smoke.py --tmp
```

## 重要设计原则

1. 用户只需要记住 `mag`。
2. `mag` 默认是交互式 Agent，不是传统参数型 CLI。
3. `/` 命令负责明确动作，自然语言负责讨论和决策。
4. LLM API 是唯一必须提前配置的 API。
5. 搜索、arXiv、数据库等 API 遵循“最少但必要”原则，需要时再配置。
6. 最终研究脚本锁定前必须检查关键数据是否可获得。
7. 找不到可靠数据时，必须提示申请 API、手动上传或修改写作思路。
8. 创建 workspace 时默认创建 Git 仓库和初始 checkpoint，防止 Agent 误删或覆盖重要文件。
9. GitHub 自动 push 是可选能力，只有用户显式开启后才同步到云端。
10. 每次重要决策都要写入 workspace。
11. 论文生成必须有可审计的研究脚本、证据、图表和 review 记录。

## 文档维护约定

- 中文文档为当前唯一维护版本。
- 英文文档以后再补。
- README 只做入口和地图，不承载全部细节。
- `design.md` 记录产品总设计。
- `docs/` 记录分模块设计。
- `docs/dev/` 记录开发者如何理解、测试和贡献代码。
- 任何新增核心模块，都必须补对应设计说明和测试入口说明。
