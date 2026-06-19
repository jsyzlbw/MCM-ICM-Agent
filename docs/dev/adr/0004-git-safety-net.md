# ADR 0004：Workspace 默认启用 Git 安全网

## 状态

Accepted

## 背景

Mag 的目标是让 Agent 在本地 workspace 中完成题目解析、数据处理、建模、图表生成、论文写作和
循环修订。为了完成这些工作，Agent 需要较高的文件读写权限。

高权限带来的风险是：Agent 可能误删、误覆盖、批量改错用户的重要文件。数学建模任务的文件又
往往包含题目、数据、模板、论文草稿和中间结果，一旦丢失会严重影响用户。

因此，workspace 需要一个默认存在、用户不需要额外理解太多的恢复机制。

## 决策

Mag 创建 workspace 时默认启用本地 Git 安全网：

1. 自动执行 `git init`。
2. 自动创建 `.gitignore`。
3. 默认排除 `.env`、缓存、敏感日志和系统临时文件。
4. 初始化完成后创建第一个 checkpoint commit。
5. Agent 每轮完成有意义修改后创建 checkpoint commit。
6. 高风险文件操作前检查 Git 状态。
7. GitHub 自动 push 作为可选能力，默认关闭，用户显式开启后才同步到云端。

## 理由

本地 Git checkpoint 能把 Agent 的高权限文件操作变成可恢复操作。用户不需要提前手动初始化
Git，也不需要在每次修改前记得备份。

GitHub 自动 push 不默认开启，因为 workspace 可能包含赛题、数据、论文草稿和用户私有信息。
云端同步应由用户明确选择，并且必须依赖 `.gitignore` 保护 `.env` 等敏感文件。

## 影响

CLI 初始化流程需要新增：

- `git init`。
- `.gitignore` 生成。
- 初始 commit。
- checkpoint 状态展示。
- `/git` 命令。

Workspace 模块需要新增或接入 workspace safety 能力：

- 创建 checkpoint。
- 检查 dirty state。
- 记录 push 状态。
- 处理 push 失败。

测试需要覆盖：

- 空目录初始化后存在 Git 仓库。
- `.env` 不进入 Git。
- 初始化后存在 checkpoint commit。
- GitHub 自动 push 默认关闭。
- push 失败不阻断本地 workflow。

## 非目标

本决策不要求 Mag 默认创建 GitHub 仓库。

本决策不要求 Mag 把每个低价值临时文件变化都提交。checkpoint 应围绕用户可理解的阶段和
有意义的修改。

本决策不把 Git 当作唯一恢复方式。未来仍可增加 trash、snapshot、artifact versioning 等机制。
