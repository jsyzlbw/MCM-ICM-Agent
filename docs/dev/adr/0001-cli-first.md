# ADR 0001：Mag 采用 CLI-first 产品形态

## 状态

Accepted

## 背景

项目早期同时有 CLI、workflow engine 和本地 GUI。GUI 能帮助观察 workflow，但用户真正高频的
入口更像 Claude Code / Codex CLI：在某个任务文件夹打开终端，输入一个命令，开始和 Agent
合作。

数学建模任务天然适合 workspace 模式：

- 一个题目对应一个文件夹。
- 有题目、数据、模板、论文、图表、日志。
- 有长期对话和多轮修订。
- 需要恢复上下文。

## 决策

Mag 的主产品入口是：

```bash
mag
```

裸 `mag` 进入交互式 CLI。GUI 降级为可选辅助，不作为当前主路径。

## 影响

正面：

- 用户只需要记住一个命令。
- 更接近开发者熟悉的 Agent CLI 体验。
- 本地文件和 workspace 模型清晰。
- 更容易支持长任务恢复和审计。

代价：

- 需要实现交互式 TUI/REPL。
- 需要重新设计 workspace 初始化体验。
- 原有 GUI API 不能作为主要产品叙事。

## 后续

- 实现裸 `mag`。
- 实现 slash command。
- 将 README 聚焦 CLI-first。
- 保留高级命令用于调试。

