# 01. CLI 产品设计

## 1. 目标

Mag 的主入口是：

```bash
mag
```

裸命令必须进入交互式 Agent，而不是只打印 help。用户不应先学习一堆参数。高级命令可以保留，
但普通用户应该从 `mag` 开始。

## 2. 启动流程

Mag 启动后按顺序做检查：

```text
读取当前目录
  -> 是否 Mag workspace
  -> 是否空目录
  -> 是否非空但不是 workspace
  -> 根据结果初始化、恢复或中止
  -> 进入交互式界面
```

### 2.1 空目录

如果当前目录为空：

1. 自动创建 workspace 结构。
2. 自动执行 `git init`。
3. 创建 `.gitignore`，确保 `.env`、缓存和临时日志不进 Git。
4. 创建 `.env`。
5. 创建 `.mag/config.toml`。
6. 创建 `.mag/state.json`。
7. 创建初始化 checkpoint commit。
8. 进入交互界面。
9. 提示用户运行 `/init`。

### 2.2 非空但不是 workspace

默认中止，并提示：

```text
当前文件夹不为空，并且没有发现 Mag workspace。
请在空文件夹中运行 mag，或显式运行 mag init --force。
```

原因：裸 `mag` 是普通用户入口，不能轻易向已有文件夹写入大量结构。

### 2.3 已有 workspace

如果发现 `.mag/workspace.json` 和 `.mag/state.json`，则恢复：

- 对话历史。
- 导入文件状态。
- 当前 workflow 阶段。
- 最近失败 gate。
- 草稿/输出状态。

## 3. 启动界面

界面应简洁，像 Claude Code / Codex CLI：

```text
╭────────────────────────────────────────────╮
│ Mag                                        │
│ MCM/ICM Modeling Agent                     │
╰────────────────────────────────────────────╯

Workspace: 2026-mcm-c
Status: init_incomplete

Type /init to set up this workspace.
Type /help to see commands.

>
```

## 4. 输入规则

| 输入 | 行为 |
|---|---|
| `/xxx` | 执行 slash command。 |
| 普通文本 | 作为自然语言消息交给 Agent。 |
| 空输入 | 不执行。 |
| `Ctrl+C` | 取消当前命令，回到主输入。 |
| `Ctrl+D` | 退出 Mag。 |

## 5. 必须支持的命令

| 命令 | 作用 | 是否需要 LLM |
|---|---|---|
| `/help` | 显示命令列表。 | 否 |
| `/api` | 查看和配置 API。 | 否 |
| `/rag` | 导入 RAG 文档。 | 否 |
| `/question` | 导入题目。 | 否 |
| `/data` | 导入题目数据。 | 否 |
| `/layout` | 导入论文模板。 | 否 |
| `/init` | 初始化 workspace 配置和资源。 | 部分需要 |
| `/start` | 开始题目分析和研究讨论。 | 是 |
| `/git` | 查看 checkpoint、远端同步和恢复状态。 | 否 |
| `/status` | 查看当前 workspace 状态。 | 否 |
| `/outputs` | 查看已生成输出。 | 否 |
| `/reset` | 清理或重置 workspace。 | 否 |

## 6. `/api`

`/api` 展示 API 状态，并允许配置。

API 分三类：

1. Required：LLM API。
2. Recommended：搜索、arXiv 或学术搜索。
3. Optional：GitHub、数据库、MinerU、embedding、humanizer 等。

LLM 是唯一必须项。没有 LLM 时，Mag 不能进行自然语言分析、题意理解和写作生成。

## 7. `/init`

`/init` 是新 workspace 的引导流程。

第一次运行：

```text
1. 配置 LLM API
2. 询问是否配置搜索
3. 询问是否配置 arXiv/学术搜索
4. 询问是否启用 GitHub 自动 push
5. 导入 RAG 文档
6. 导入题目
7. 导入数据
8. 导入模板
9. 确认输出语言和偏好
```

非第一次运行：

```text
This workspace has already been initialized.

1. Cancel
2. Re-think only: 清理对话和生成历史，保留 API/RAG/input
3. Full reset: 清空 API、RAG、input、work、output
```

## 8. `/start`

`/start` 进入题目分析和研究讨论。

执行前必须满足：

- LLM API 已配置。
- 题目已导入。

不强制满足：

- 搜索 API。
- 数据库 API。
- RAG 文档。
- 模板。

如果缺少推荐项，Mag 只提示，不阻断：

```text
Search API 尚未配置。之后如果需要联网检索，我会再提示你配置。
现在可以继续。
```

## 9. 自然语言守卫

如果用户未完成初始化就直接聊天：

```text
> 帮我分析这个题
```

Mag 检查状态：

- 没有 LLM：提示配置 `/api`。
- 没有题目：提示 `/question`。
- 未完成 `/init` 但已满足基本条件：允许继续，同时提示还可以补充 RAG/data/layout。

## 10. 高级传统命令

为了脚本化和调试，保留高级命令：

```bash
mag -v
mag init
mag status
mag inspect
mag run
mag resume
mag package
mag provider-status
mag provider-smoke
```

这些命令面向开发者和自动化流程。用户文档中应优先介绍裸 `mag`。

## 11. Git 安全网

裸 `mag` 创建 workspace 时必须默认启用本地 Git 安全网。CLI 层需要提供清晰反馈：

```text
Git safety net: enabled
Initial checkpoint: created
Remote sync: disabled
```

每次 Agent 完成一轮文件修改，应触发 checkpoint：

```text
Checkpoint created: 2026-06-19 21:30 research script locked
```

如果用户启用了 GitHub 自动 push，checkpoint 后继续 push：

```text
Checkpoint pushed to GitHub.
```

如果 push 失败，不阻断本地建模流程：

```text
Local checkpoint created, but GitHub push failed.
Run /git for details.
```

`/git` 至少应支持：

- 查看本地 checkpoint 状态。
- 查看是否有未提交修改。
- 查看 remote 是否配置。
- 开启或关闭自动 push。
- 展示最近一次 push 错误。
