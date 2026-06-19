# 测试指南

## 1. 基本命令

运行全量测试：

```bash
pytest -q
```

运行 lint：

```bash
ruff check src tests
```

运行某个测试文件：

```bash
pytest tests/test_cli_config.py -q
```

运行 CLI-first smoke：

```bash
python scripts/run_cli_smoke.py --tmp
```

## 2. 新功能测试原则

新增行为应先写测试。测试应回答：

- 用户输入什么。
- 系统输出什么。
- 哪些文件被创建。
- 哪些状态被更新。
- 失败时如何表现。

不要只测试内部函数名和实现细节。

## 3. CLI 测试

使用 Typer 的 `CliRunner`：

```python
from typer.testing import CliRunner
from mcm_agent.cli import app

def test_version():
    result = CliRunner().invoke(app, ["-v"])
    assert result.exit_code == 0
    assert "mag" in result.output
```

交互输入：

```python
result = runner.invoke(app, ["init"], input="y\n")
```

## 4. Workspace 测试

使用 `tmp_path`，不要写真实用户目录：

```python
def test_workspace(tmp_path):
    workspace = create_workspace(tmp_path / "task")
    assert (workspace.root / "task_state.json").exists()
```

未来新 workspace 结构应测试：

- 空目录初始化。
- 非空非 workspace 中止。
- 已有 workspace 恢复。
- reset/rethink 行为。
- `.mag/workspace.json` 和 `.mag/state.json`。
- Git checkpoint 和 `.gitignore`。

## 5. Provider 测试

默认使用 fake provider。真实 API 测试只能作为 smoke，不应进入默认 CI。

Provider 测试应覆盖：

- 有 key 时启用。
- 无 key 时 fake/skip。
- 错误信息脱敏。
- 单 provider 失败不会污染其他 provider。

## 6. Agent 测试

Agent 测试应构造最小 workspace 文件，然后运行 agent，检查输出 artifact。

重点检查：

- 输出文件存在。
- JSON schema 合法。
- gate decision 正确。
- 失败时 blocker 可读。

## 7. Workflow 测试

Workflow 测试应优先使用 fake/demo provider。

目标：

- 端到端能完成。
- gate 失败能路由。
- resume 能从指定 stage 继续。
- repeated failure 能 blocked。

## 8. 文档测试

文档测试用于保护关键入口不漂移。

应检查：

- README 指向核心文档。
- 必须命令出现在文档中。
- 新模块有对应设计文档。

## 9. CLI-first 新测试入口

| 测试 | 覆盖 |
|---|---|
| `tests/test_install_script.py` | 一键安装脚本。 |
| `tests/test_cli_interactive.py` | 裸 `mag`、恢复、slash dispatch。 |
| `tests/test_workspace_v2.py` | 新 workspace layout。 |
| `tests/test_workspace_safety.py` | Git 安全网。 |
| `tests/test_import_commands.py` | `/question`、`/data`、`/layout`、`/rag`。 |
| `tests/test_init_command.py` | `/init`、rethink、full reset。 |
| `tests/test_session_store.py` | 对话与事件落盘。 |
| `tests/test_dialogue_guard.py` | 自然语言守卫。 |
| `tests/test_research_script.py` | `/start` 和 research script。 |
| `tests/test_workflow_adapter.py` | 新旧 workflow 适配。 |
| `tests/test_github_sync.py` | 可选 GitHub auto push。 |
| `tests/test_revision_loop.py` | 用户反馈生成 revision plan。 |
| `tests/test_permissions.py` | 文件操作权限策略。 |
| `tests/test_cli_e2e.py` | CLI-first 端到端 smoke。 |

## 10. 什么时候跑全量测试

必须跑全量测试：

- 修改 core models。
- 修改 workspace schema。
- 修改 workflow graph。
- 修改 CLI entry point。
- 修改 provider factory。
- 删除或移动文件。

可以跑局部测试：

- 只修改文档。
- 只修改某个 prompt。
- 只改某个 isolated agent，并且全量在最终合并前再跑。
