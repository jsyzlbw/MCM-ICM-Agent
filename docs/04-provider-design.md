# 04. Provider 与 API 设计

## 1. 目标

Mag 需要调用多种外部能力，但不能要求用户一开始配置一大堆 API。设计原则是：

```text
LLM 必须
高概率用到的 API 推荐
专业数据库按需提示
能跳过的就允许跳过
```

## 2. Provider 分类

| 类别 | 是否必需 | 用途 |
|---|---|---|
| LLM | 必需 | 对话、题意理解、研究脚本、写作。 |
| Search | 推荐 | 搜索公开数据和网页资料。 |
| arXiv/学术搜索 | 推荐 | 查找论文、方法和参考资料。 |
| Firecrawl/Web extract | 可选 | 抽取网页正文。 |
| MinerU/PDF parsing | 可选 | 更强题面和 PDF 解析。 |
| Voyage/Embedding | 可选 | RAG embedding 和 rerank。 |
| 官方数据库 | 按需 | FRED、NOAA、Census、World Bank 等。 |
| GitHub | 可选 | 将本地 checkpoint commit 自动 push 到用户指定仓库。 |
| LaTeX | 本地依赖 | 编译论文。 |
| Humanizer | 可选 | 风格统一和自然化，不用于规避检测。 |

## 3. 最少但必要原则

### 初始化阶段

`/init` 阶段只强制 LLM：

```text
LLM API 尚未配置。Mag 需要 LLM API 才能与你讨论题目和生成方案。
是否现在配置？ [Y/n]:
```

Search 和 arXiv 只推荐：

```text
Search API 可以帮助 Mag 查找公开数据和参考资料。
现在配置吗？ [y/N]:
```

GitHub 自动 push 只作为可选安全增强：

```text
Mag 已经为本 workspace 创建本地 Git checkpoint。
是否额外启用 GitHub 自动 push，把每次 checkpoint 同步到远端？ [y/N]:
```

### 讨论阶段

当 Agent 发现需要某个专业数据源时再提示：

```text
这份研究脚本需要历史气象数据。
NOAA 或 NASA POWER 可能适合。
是否配置相关 API？
```

## 4. 配置文件

Secret 写入 `.env`：

```dotenv
MAG_LLM_API_KEY=
MAG_SEARCH_API_KEY=
MAG_ARXIV_API_KEY=
MAG_NOAA_API_KEY=
MAG_FRED_API_KEY=
MAG_GITHUB_TOKEN=
```

非 secret 写入 `.mag/config.toml`：

```toml
[llm]
provider = "openai_compatible"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1"

[search]
enabled = false
provider = "tavily"

[git]
enabled = true
checkpoint = true
auto_push = false
remote = "origin"
branch = "main"
```

## 5. `/api` 展示

`/api` 应展示：

- 已配置。
- 未配置。
- 已选择暂不启用。
- 本阶段推荐配置。
- 某个 provider 最近一次 smoke 结果。

示例：

```text
Required:
  [ok]      LLM          gpt-4.1

Recommended:
  [missing] Search       useful for public data
  [skipped] arXiv        skipped by user

Need later:
  [disabled] GitHub      local checkpoint only
  [missing] NOAA         not needed yet
  [missing] FRED         not needed yet
```

## 6. Provider Smoke

每个 provider 都应有轻量 smoke：

- 不泄露 key。
- 不产生高成本请求。
- 结果写入 `.mag/logs/provider_smoke_history.jsonl`。

Smoke 结果：

```json
{
  "provider": "llm",
  "status": "passed",
  "detail": "model responded",
  "created_at": "..."
}
```

## 7. 失败策略

| 失败 | 行为 |
|---|---|
| LLM 不可用 | 阻止对话和 `/start`。 |
| Search 不可用 | 允许继续，但不能做联网搜索。 |
| 数据库 API 不可用 | 给出手动上传或换思路选项。 |
| Firecrawl 不可用 | 可退化为搜索摘要或用户上传资料。 |
| Embedding 不可用 | 退化为关键词检索。 |

## 8. 隐私与安全

- 不在日志中打印 API key。
- `.env` 必须在 `.gitignore` 中。
- GitHub 自动 push 默认关闭，必须由用户显式开启。
- 自动 push 前必须确认 `.gitignore` 已排除 `.env` 和本地敏感缓存。
- 导出 bug report 时默认不包含 `.env`。
- provider 错误信息要脱敏。
