# 开发路线图

## P0：完成 CLI-first 产品入口

目标：用户输入裸 `mag` 后进入交互式 Agent。

任务：

- 当前目录 workspace 检测。
- 空目录自动初始化。
- workspace 创建时自动 `git init`。
- 创建 `.gitignore`，排除 `.env`、缓存和敏感日志。
- 初始化后创建第一个 checkpoint commit。
- 非空非 workspace 目录提示。
- 已有 workspace 恢复。
- 交互式输入循环。
- `/help`。
- `/status`。
- 基础状态持久化。

## P1：完成初始化向导

目标：用户通过 `/init` 完成最少必要配置和资源导入。

任务：

- `/api` 配置 LLM。
- `.env` secret 写入。
- `.mag/config.toml` 非 secret 写入。
- `/git` 查看 checkpoint 和远端同步状态。
- 可选启用 GitHub 自动 push。
- `/question` 导入题目。
- `/data` 导入数据。
- `/layout` 导入模板。
- `/rag` 导入知识库文档。
- init state 更新。

## P2：自然语言对话守卫

目标：未满足条件时给出正确提示，而不是让 Agent 失败。

任务：

- 未配置 LLM 时拦截。
- 未导入题目时提示。
- 推荐 API 缺失时非阻塞提示。
- 对话历史写入 `.mag/chat/messages.jsonl`。
- 对话摘要机制。

## P3：研究脚本和数据可得性检查

目标：锁定论文脚本前先判断关键数据是否可获得。

任务：

- 生成 `research_script.md/json`。
- 从讨论中提取 data needs。
- 检查用户数据、RAG、搜索、官方 API。
- 输出 data availability matrix。
- 找不到数据时给 API 申请或换思路建议。
- 用户确认 locked script。

## P4：接入现有 workflow

目标：从交互式 CLI 启动当前 workflow engine。

任务：

- 将新 workspace 结构映射到当前 workflow 输入。
- 复用 StageExecutor。
- 将 artifacts 写入 `work/`。
- 将用户可读结果复制到 `output/`。
- 在 CLI 中展示阶段进度。

## P5：修订循环

目标：用户反馈后能局部重跑和重新生成论文。

任务：

- 解析用户反馈。
- 生成 revision script。
- 用户确认。
- 选择最小重跑阶段。
- 保存 revision history。
- 输出新 draft。

## P6：真实 provider 端到端验收

目标：用真实 LLM、搜索、RAG 和小型题目跑通。

任务：

- provider smoke 体验打磨。
- 错误信息脱敏。
- 成本记录。
- timeout 和 retry 策略。
- 失败恢复文档。

## P7：GitHub 同步和恢复体验

目标：让用户能放心给 Agent 较高权限，并在需要时云端备份。

任务：

- checkpoint commit 策略。
- 高风险写入前 Git 状态检查。
- GitHub remote 配置向导。
- 自动 push 开关。
- push 失败提示和重试。
- 从 checkpoint 恢复的用户指引。

## P8：英文文档和安装脚本

目标：项目可对外发布。

任务：

- `install.sh`。
- GitHub README 安装说明。
- 英文 README。
- 英文 docs。
- 示例 demo workspace。
