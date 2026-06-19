# 02. Workspace 设计

## 1. 目标

Workspace 是 Mag 的本地工作状态边界。一个 workspace 对应一次数学建模任务。用户在同一个
文件夹再次输入 `mag`，应该能恢复之前的对话、资源、计划、运行结果和论文草稿。

## 2. 推荐目录结构

```text
.
├── .git/
├── .gitignore
├── .env
├── .mag/
│   ├── workspace.json
│   ├── state.json
│   ├── config.toml
│   ├── chat/
│   │   ├── messages.jsonl
│   │   └── sessions/
│   ├── logs/
│   └── cache/
├── input/
│   ├── problem/
│   ├── data/
│   ├── layout/
│   └── notes/
├── knowledge/
│   ├── papers/
│   ├── methods/
│   ├── rules/
│   └── cases/
├── work/
│   ├── parsed/
│   ├── reports/
│   ├── discussion/
│   ├── data/
│   ├── results/
│   ├── figures/
│   ├── paper/
│   └── review/
└── output/
    ├── draft/
    ├── final/
    └── package/
```

## 3. 顶层目录职责

| 路径 | 是否用户直接关心 | 职责 |
|---|---|---|
| `.git/` | 一般不直接改 | 本地 checkpoint 历史，用于恢复 Agent 误删或误改的文件。 |
| `.gitignore` | 部分关心 | 控制哪些 secret、缓存、临时文件不进入 Git。 |
| `.env` | 部分关心 | 保存 API key，不进 Git。 |
| `.mag/` | 一般不直接改 | 保存 Mag 自身状态、配置、对话、日志、缓存。 |
| `input/` | 关心 | 用户导入的题目、数据、模板和说明。 |
| `knowledge/` | 关心 | 用户导入的 RAG 文档。 |
| `work/` | 调试时关心 | Agent 中间产物和可审计证据链。 |
| `output/` | 关心 | 用户最终查看的草稿、终稿、提交包。 |

## 4. `.mag/workspace.json`

记录 workspace 元信息：

```json
{
  "schema_version": 1,
  "workspace_id": "2026-mcm-c",
  "created_at": "2026-06-19T10:00:00+08:00",
  "updated_at": "2026-06-19T11:20:00+08:00",
  "mag_version": "0.1.0",
  "status": "initialized"
}
```

用途：

- 判断当前目录是否 Mag workspace。
- 判断 workspace schema 是否需要迁移。
- 展示启动摘要。

## 5. `.mag/state.json`

记录当前任务状态：

```json
{
  "init": {
    "completed": false,
    "llm_configured": false,
    "problem_imported": false,
    "rag_documents": 0,
    "data_files": 0,
    "layout_imported": false
  },
  "phase": "init_incomplete",
  "problem": null,
  "last_stage": null,
  "blocked_reason": null
}
```

状态必须足够轻量，不保存大段正文。大段内容写入对应 artifact 文件。

## 6. `.mag/config.toml`

保存非 secret 配置：

```toml
[llm]
provider = "openai_compatible"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1"
enabled = true

[search]
enabled = false

[runtime]
language = "en"
auto_approve = false
```

API key 不写入 `config.toml`，只写 `.env`。

## 7. Git 安全网

Mag 创建 workspace 时必须默认初始化本地 Git 仓库：

```bash
git init
```

随后创建 `.gitignore`，至少包含：

```gitignore
.env
.mag/cache/
.mag/logs/*.debug.json
.mag/logs/*raw*
__pycache__/
.DS_Store
```

初始化完成后，Mag 创建第一个 checkpoint commit：

```text
mag workspace initialized
```

### 7.1 Checkpoint 策略

Agent 每轮完成有意义的文件修改后，应创建 checkpoint commit。典型 checkpoint 包括：

- workspace 初始化完成。
- `/question`、`/data`、`/layout`、`/rag` 导入完成。
- `/init` 完成。
- research script 被用户确认。
- workflow 关键阶段完成。
- 用户反馈修订完成。
- final package 生成完成。

commit message 应简短、可读，例如：

```text
mag: import problem statement
mag: lock research script
mag: generate draft v2
```

### 7.2 高风险写入前检查

当 Agent 准备执行删除、覆盖、批量移动、批量重写等高风险文件操作时，必须先检查 Git 状态。

推荐规则：

- 如果工作区干净，可以继续操作，并在操作后提交 checkpoint。
- 如果存在未提交改动，先自动提交 checkpoint，或者提示用户确认。
- `.env` 和其他 ignored 文件不应被提交，但如果高风险操作会影响它们，必须单独提示用户。

### 7.3 GitHub 自动 push

GitHub 远端同步是可选能力，不默认开启。用户开启后，Mag 在每个 checkpoint commit 后尝试
push 到远端。

配置建议写入 `.mag/config.toml`：

```toml
[git]
enabled = true
checkpoint = true
auto_push = false
remote = "origin"
branch = "main"
```

GitHub token 或凭据不写入 `config.toml`，只能通过系统 Git credential、GitHub CLI 或 `.env`
中的 secret 读取。`.env` 仍然必须被 `.gitignore` 排除。

如果 push 失败，Mag 不应回滚本地 commit，也不应中止建模流程。它应该记录错误并在 CLI 中提示：

```text
本地 checkpoint 已保存，但 GitHub 自动 push 失败。可稍后运行 /git 查看。
```

## 8. 对话历史

`.mag/chat/messages.jsonl` 每行一条消息：

```json
{"role":"user","content":"我想用多目标优化","created_at":"..."}
{"role":"assistant","content":"可以，但需要检查数据...","created_at":"..."}
```

用途：

- 恢复上下文。
- 生成修订脚本。
- 审计关键决策。

不应该无限增长地塞进 LLM 上下文。运行时应做摘要和检索。

## 9. 输入目录

### `input/problem/`

保存题目文件。通常只有一个主题目文件。

### `input/data/`

保存题目给定的数据。可以是 CSV、Excel、ZIP、文件夹。

### `input/layout/`

保存模板和格式要求，例如 `.tex`、`.cls`、`.sty`、`.docx`、官方 PDF。

### `input/notes/`

保存用户额外要求，例如：

- 想采用的模型。
- 想规避的方向。
- 老师要求。
- 论文语言偏好。

## 10. Knowledge 目录

RAG 文档按用途组织：

| 子目录 | 内容 |
|---|---|
| `knowledge/papers/` | 优秀论文、参考论文。 |
| `knowledge/methods/` | 方法笔记、模型说明。 |
| `knowledge/rules/` | 比赛规则、格式要求、评分标准。 |
| `knowledge/cases/` | 过往案例和复盘。 |

每个导入文档应记录 metadata：

```json
{
  "document_id": "rag_001",
  "workspace_path": "knowledge/papers/example.pdf",
  "type": "paper",
  "usage": "methodology_guidance",
  "indexed": true
}
```

## 11. Work 目录

`work/` 是 Agent 的工作台。它保存可审计中间产物：

| 子目录 | 作用 |
|---|---|
| `work/parsed/` | 题面解析结果。 |
| `work/reports/` | 题意、数据、模型、验证报告。 |
| `work/discussion/` | 研究脚本、方向锁定、用户确认。 |
| `work/data/` | 外部来源、lineage、processed data。 |
| `work/results/` | 模型运行结果和证据。 |
| `work/figures/` | 图表计划、源文件和输出。 |
| `work/paper/` | LaTeX 源和章节。 |
| `work/review/` | gate、审稿、证据绑定、排版 QA。 |

## 12. Output 目录

`output/` 面向用户：

```text
output/
  draft/
    main.pdf
    reviewer_report.md
  final/
    main.pdf
    main.tex
  package/
    submission_package.zip
```

原则：

- `work/` 可以复杂。
- `output/` 必须清晰。
- 用户最常打开的是 `output/draft/main.pdf` 和 `output/package/submission_package.zip`。

## 13. Reset 策略

### 重新思考

清理：

- `.mag/chat/`
- `work/`
- `output/`

保留：

- `.env`
- `.mag/config.toml`
- `input/`
- `knowledge/`

### 完全重置

清理：

- `.mag/`
- `.env`
- `input/`
- `knowledge/`
- `work/`
- `output/`

必须要求用户输入 `RESET` 二次确认。
