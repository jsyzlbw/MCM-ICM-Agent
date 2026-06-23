# Mag

Mag 是一个面向 MCM/ICM 数学建模论文的本地命令行 Agent。当前文档系统以中文为准，英文版后续再补。

一键安装：

```bash
curl -fsSL https://raw.githubusercontent.com/jsyzlbw/MCM-ICM-Agent/main/install.sh | bash
```

请从这里开始阅读：

- [中文 README](README.zh-CN.md)
- [总设计文档](design.md)
- [文档索引](docs/README.md)

开发环境快速验证：

```bash
python -m pip install -e ".[dev]"
mag -v
pytest -q
ruff check src tests
```

## MCM/ICM 优秀论文知识库（开箱即用）

仓库内置一套 MCM/ICM **O 奖论文知识库**（451 篇 Outstanding 论文，2004–2025），三层结构，已随仓库发布在 `corpus_kb/`：

- `corpus_kb/markdown/` — 每篇论文 MinerU 提取的 Markdown（公式转 LaTeX）
- `corpus_kb/teardowns/` — 每篇一张结构化拆解卡 `TeardownCard`（模型 / 为何获奖 / 写作亮点 / 硬伤 / 可复用范式）
- `corpus_kb/patterns/` — 按 8 个题型聚合的范式库
- `corpus_kb/manifest.json` — 论文清单与元数据（year / contest / problem / problem_type / award）

三种用法：

**(a) 零依赖浏览** —— 直接读 JSON，不需要任何 key 或安装：

```bash
cat corpus_kb/teardowns/2025-2522820.json     # 单篇拆解卡
cat corpus_kb/patterns/data.json              # 某题型的范式
```

**(b) 语义检索**（`mag kb query` / `mag kb teardown`）—— 需要配置 **Voyage API key**（用于把查询嵌入向量），并先下载向量库（见下）：

```bash
export VOYAGE_API_KEY=...                      # 或写进 workspace .env
mag kb query "robust optimization under uncertainty" --kb corpus_kb --top-k 5
mag kb status --kb corpus_kb
```

向量库 `corpus_kb/chroma/`（410M，含 >100MB 文件）**不随 git 发布**，作为 GitHub Release 附件提供，开箱即用无需重建：

```bash
# 从 Releases 下载 corpus_kb_chroma.tar.gz 后：
tar -xzf corpus_kb_chroma.tar.gz -C corpus_kb     # 解出 corpus_kb/chroma/
```

**(c) 换用别的嵌入模型** —— 用随仓库发布的 `markdown/` 重建向量库（不需要下载附件）：

```bash
mag kb build --kb corpus_kb                    # 重新切分 + 嵌入 + 入 ChromaDB（collection: mcm_corpus）
```

> 原始论文 PDF（`assets/mcm_icm_corpus/`，4.4G）受版权限制，不随仓库发布。
