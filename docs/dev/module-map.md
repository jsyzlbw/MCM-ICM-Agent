# 模块地图

## 1. `src/mcm_agent/cli.py`

命令行入口：

- `mag` 裸命令进入交互式 CLI。
- `mag -v` 输出版本。
- `mag init` 初始化当前目录。
- `mag inspect`、`mag run`、`mag resume`、`mag provider-smoke` 作为高级调试入口保留。

相关测试：

- `tests/test_cli_config.py`
- `tests/test_cli_interactive.py`

## 2. `src/mcm_agent/cli_session.py`

交互式 CLI session：

- 空目录裸 `mag` 初始化 workspace。
- 非空非 workspace 目录阻断。
- 已有 workspace 恢复。
- `/` 命令分发。
- 自然语言守卫。
- 会话消息和命令事件落盘。

相关测试：

- `tests/test_cli_interactive.py`
- `tests/test_session_store.py`
- `tests/test_dialogue_guard.py`

## 3. `src/mcm_agent/cli_commands/`

Slash command 模块：

| 文件 | 职责 |
|---|---|
| `base.py` | command context/result 协议。 |
| `api.py` | `/api` 状态展示。 |
| `git.py` | `/git` checkpoint 和 auto push 状态。 |
| `imports.py` | `/question`、`/data`、`/layout`、`/rag`。 |
| `init.py` | `/init`、rethink、full reset。 |
| `start.py` | `/start`、research script、workflow adapter 触发。 |
| `status.py` | `/status`、`/outputs`。 |

相关测试：

- `tests/test_import_commands.py`
- `tests/test_init_command.py`
- `tests/test_research_script.py`
- `tests/test_status_outputs.py`
- `tests/test_github_sync.py`

## 4. `src/mcm_agent/config.py`

配置加载。当前支持：

- `.env`
- JSON config
- JSON 覆盖 env

后续继续增强：

- `/api` 写配置。
- workspace-local `.env` 与 `.mag/config.toml` 的完整合并策略。

相关测试：

- `tests/test_config_json.py`
- `tests/test_config_merge.py`
- `tests/test_cli_config.py`

## 5. Core 模块

| 文件 | 职责 | 相关测试 |
|---|---|---|
| `workspace.py` | 创建新 CLI-first workspace 和旧 workflow 兼容结构。 | `tests/test_workspace_v2.py`, `tests/test_workspace_registry.py` |
| `workspace_models.py` | workspace metadata/state/resource Pydantic model。 | `tests/test_workspace_v2.py` |
| `workspace_safety.py` | Git init、`.gitignore`、checkpoint、auto push。 | `tests/test_workspace_safety.py`, `tests/test_github_sync.py` |
| `imports.py` | 文件复制、目录导入、metadata、冲突命名。 | `tests/test_import_commands.py` |
| `session_store.py` | `.mag/chat/messages.jsonl`、`.mag/events.jsonl`、summary。 | `tests/test_session_store.py` |
| `dialogue_guard.py` | 自然语言对话前置条件。 | `tests/test_dialogue_guard.py` |
| `research_script.py` | research script 和 data availability matrix。 | `tests/test_research_script.py` |
| `workflow_adapter.py` | 新 workspace layout 到现有 MVP workflow 的适配。 | `tests/test_workflow_adapter.py`, `tests/test_cli_e2e.py` |
| `permissions.py` | 文件操作风险分级。 | `tests/test_permissions.py` |
| `revision_plan.py` | 用户反馈后的 revision plan。 | `tests/test_revision_loop.py` |
| `stage_executor.py` | stage 执行、gate 路由、重复失败保护。 | `tests/test_stage_executor.py` |
| `workflow_graph.py` | 默认 workflow graph。 | `tests/test_workflow_topology.py` |

## 6. `src/mcm_agent/agents/`

Agent 文件职责：

| 文件 | 职责 |
|---|---|
| `intake.py` | 输入复制和 manifest。 |
| `extraction.py` | 题面抽取和 extraction gate。 |
| `problem_understanding.py` | 题意理解。 |
| `data_feasibility.py` | 数据可得性检查。 |
| `discussion.py` | 用户方向确认。 |
| `rag.py` | RAG 导入和检索。 |
| `modeling.py` | 候选模型和模型裁决。 |
| `modeling_quality.py` | 模型计划质量 gate。 |
| `search_data.py` | 数据搜索、source registry、source gate。 |
| `eda.py` | 数据画像。 |
| `solver.py` | 求解和 evidence registry。 |
| `validation.py` | 结果验证。 |
| `visualization.py` | 图表规划和生成。 |
| `figure_quality.py` | 图表质量 gate。 |
| `claim_planning.py` | claim plan。 |
| `writer.py` | LaTeX 写作。 |
| `paper_evidence.py` | 论文证据绑定。 |
| `reference_manager.py` | BibTeX 和引用审计。 |
| `typesetting_qa.py` | 排版 QA。 |
| `typesetting_repair.py` | 排版修复。 |
| `reviewer.py` | 最终审稿。 |
| `submission.py` | 打包。 |
| `revision.py` | 旧修订能力，后续与 `core/revision_plan.py` 打通。 |

## 7. `src/mcm_agent/providers/`

Provider 文件职责：

| 文件 | 职责 |
|---|---|
| `base.py` | ProviderBundle 和基础协议。 |
| `factory.py` | 根据配置构建 providers。 |
| `llm.py` | LLM provider。 |
| `search.py` | 搜索和网页抽取。 |
| `mineru.py` | PDF parsing provider。 |
| `data_apis.py` | 官方数据 API。 |
| `embedding.py` | embedding/rerank。 |
| `latex.py` | LaTeX 编译。 |
| `humanizer.py` | 文本自然化。 |
| `github.py` | 可选 GitHub checkpoint push adapter。 |
| `smoke.py` | provider smoke。 |

## 8. `src/mcm_agent/solver_modules/`

Solver module 文件职责：

| 文件 | 职责 |
|---|---|
| `evaluation.py` | 多指标评价。 |
| `optimization.py` | 约束优化。 |
| `forecasting.py` | 预测。 |
| `simulation.py` | 仿真。 |
| `classification.py` | 分类。 |
| `clustering.py` | 聚类。 |
| `queuing.py` | 排队论。 |
| `network.py` | 网络流/图模型。 |

## 9. `src/mcm_agent/server/`

当前本地 GUI API。CLI-first 产品成熟前，server 层作为可选能力维护。

重点测试：

- `tests/test_server_config.py`
- `tests/test_server_workspace.py`
- `tests/test_server_workflow_control.py`
- `tests/test_server_knowledge.py`
- `tests/test_server_static.py`

## 10. 脚本和示例

| 文件 | 职责 |
|---|---|
| `install.sh` | 一键安装 `mag`。 |
| `scripts/run_cli_smoke.py` | CLI-first 端到端 smoke。 |
| `examples/demo_problem/` | smoke 使用的最小 demo 题目和数据。 |
