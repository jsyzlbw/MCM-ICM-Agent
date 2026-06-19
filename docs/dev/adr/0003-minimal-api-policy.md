# ADR 0003：采用最少但必要的 API 配置策略

## 状态

Accepted

## 背景

数学建模 Agent 可能使用很多外部服务：

- LLM
- 搜索
- arXiv
- 网页抽取
- PDF 解析
- embedding
- 官方数据库
- LaTeX
- humanizer

如果初始化时要求用户一次性配置所有 API，会导致上手困难。很多 API 只有特定题目才需要。

## 决策

只有 LLM API 是启动 Agent 分析能力的强制项。其他 API 按需启用：

- Search、arXiv：推荐，但可跳过。
- 数据库 API：分析题目发现需要时再提示。
- MinerU、embedding、Firecrawl、humanizer：阶段需要时再提示或降级。

## 影响

正面：

- 降低上手门槛。
- 避免用户配置无关 API。
- 让 API 配置和题目需求绑定。

代价：

- workflow 中需要更多 capability check。
- provider 缺失时需要优雅降级。
- Agent 需要清楚告诉用户“缺什么会影响什么”。

## 后续

- `/api` 展示 required/recommended/optional。
- `/start` 前只强制检查 LLM 和题目。
- 数据可得性检查阶段动态建议专业 API。

