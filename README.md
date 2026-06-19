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
