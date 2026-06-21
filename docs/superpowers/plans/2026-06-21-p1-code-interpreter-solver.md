# P1 求解器升级为有状态 Code-Interpreter 环 + P0 收尾 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 mag 的「一次性 LLM 代码生成」求解器升级为**有状态 Jupyter Code-Interpreter 多轮 ReAct 环**（追平并反超 MathModelAgent 的唯一真优势），并收尾 P0 的最后一个缺口（PQ4 在 LLM 路径的敏感性兜底）。

**Architecture:** 新增 `tools/code_interpreter.py`：一个 `CodeInterpreter` 协议 + 一个基于 `jupyter_client` 的持久 kernel 实现（跨 cell 保留变量、落 `notebook.ipynb`）。`SolverCoderAgent` 新增 `_run_interpreter_loop`：用**文本协议 ReAct**（模型发 ```python 块 → 我们在 kernel 执行 → 把真实 stdout/错误回灌 → 模型反思续写 → 直到 DONE），按 `ModelSpec` 子问题分段，成功路径做确定性正确性自评（B3）。`run()` 的降级链：Code-Interpreter 环 → 现有一次性 codegen（无 jupyter 时）→ 模板兜底。完全向后兼容、headless 可降级。

**Tech Stack:** Python 3.12，`jupyter_client` + `ipykernel` + `nbformat`（新增依赖），现有 `pandas/numpy/scipy/sklearn/matplotlib`，provider 接口 `generate(system, prompt)->ProviderResult`（不改）。

## Global Constraints

- **不改 provider 接口**：ReAct 环只用现有 `llm_provider.generate(system, prompt, *, temperature=0.2) -> ProviderResult(content, metadata)`，多轮靠累积 transcript 字符串实现（无需 tool-calling）。
- **向后兼容 & 可降级**：无 `llm_provider` 时走模板兜底；`jupyter_client`/kernel 不可用时回落到现有一次性 `_run_llm_codegen`（subprocess），再回落模板兜底。**现有 ~531+ 测试必须全绿。**
- **不伪造数字**：所有写入 `results/*.json|csv` 的指标必须来自真实执行；敏感性兜底沿用现有 `_run_sensitivity_sweep`（列名 `input_mean_proxy` 表示输入稳定性代理，非主指标）。
- **沙箱**：每个 cell 有超时；kernel cwd=workspace；prompt 层禁网（与现状一致）。kernel 总时长有上限。
- **不碰 assets/**；提交只含 `src/`、`tests/`、`docs/`、`pyproject.toml`；**绝不 `git add -A`**。keys 在 `.env`/gitignored config。
- 提交信息结尾：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 测试用 fake LLM（参考 `tests/test_solver_codegen.py::_ScriptLLM`）与 fake 解释器（in-process `exec`，见 Task B1），**不**在单测里起真 kernel；真 kernel 只在一个可跳过的集成测试里验证。

---

## 文件结构

- **新建** `src/mcm_agent/tools/__init__.py`（若不存在）
- **新建** `src/mcm_agent/tools/code_interpreter.py` — `ExecResult`、`CodeInterpreter` 协议、`JupyterCodeInterpreter`
- **修改** `src/mcm_agent/agents/solver.py` — 新增 `_run_interpreter_loop` + 成功路径自评 + 降级链；LLM 路径收尾敏感性兜底
- **修改** `pyproject.toml` — 新增 `jupyter_client`、`ipykernel`、`nbformat`
- **新建** `tests/test_code_interpreter.py`、`tests/test_solver_interpreter_loop.py`、`tests/test_code_interpreter_jupyter_integration.py`
- **修改** `tests/`（若 PQ4 兜底需新断言）`tests/test_sensitivity_fallback.py`
- mvp.py 的 `solver_coder` 阶段**不改**（已调用 `SolverCoderAgent.run()`；`refine_from_code` 仍在其后）

---

## Track A — P0 收尾（小、先做，给后续一个干净基线）

### Task A1: LLM 路径收尾敏感性兜底（修 PQ4 缺口）

**Files:**
- Modify: `src/mcm_agent/agents/solver.py`（`_run_llm_codegen` 成功分支，约 105-120 行；`run()` 约 22-26 行）
- Test: `tests/test_sensitivity_fallback.py`

**Interfaces:**
- Consumes: 现有 `SolverCoderAgent._run_sensitivity_sweep(workspace_root, processed_file)`（solver.py:417）
- Produces: 保证**任何成功的求解路径**（LLM 或模板）结束时 `results/sensitivity_analysis.csv` 都有 ≥3 行真实数据

**背景**：现状 `_run_llm_codegen` 成功后直接 `_record_outputs` 返回（solver.py:23-26），若 LLM 脚本没写出合法 `sensitivity_analysis.csv`，敏感性表为空。模板路径已在末尾调 `_run_sensitivity_sweep`（solver.py:414），LLM 路径没有。

- [ ] **Step 1: 写失败测试** — `tests/test_sensitivity_fallback.py` 新增 `test_llm_path_backfills_sensitivity_when_llm_csv_missing`：

```python
def test_llm_path_backfills_sensitivity_when_llm_csv_missing(tmp_path):
    # 构造一个 workspace，processed CSV 有数值列；LLM 脚本写 results.csv + model_metrics.json，但 NOT sensitivity
    ws = _make_workspace(tmp_path)  # 复用本文件已有的 workspace 搭建 helper（若无则内联）
    proc = ws / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    pd.DataFrame({"region": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]}).to_csv(proc / "d.csv", index=False)

    class _LLM:  # 写出结果但故意不写 sensitivity_analysis.csv
        def generate(self, system, prompt, *, temperature=0.2):
            from mcm_agent.providers.base import ProviderResult
            code = (
                "import json, pandas as pd\n"
                "from pathlib import Path\n"
                "df = sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0]\n"
                "df = pd.read_csv(df)\n"
                "df.to_csv('results/problem1_results.csv', index=False)\n"
                "Path('results').mkdir(exist_ok=True)\n"
                "json.dump({'value_mean': float(df['value'].mean())}, open('results/model_metrics.json','w'))\n"
            )
            return ProviderResult(content=f"```python\n{code}```", metadata={})

    SolverCoderAgent(llm_provider=_LLM()).run(ws)
    sens = ws / "results" / "sensitivity_analysis.csv"
    assert sens.exists()
    assert len(pd.read_csv(sens)) >= 3
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_sensitivity_fallback.py::test_llm_path_backfills_sensitivity_when_llm_csv_missing -v` → FAIL（sensitivity 不存在）
- [ ] **Step 3: 最小实现** — 在 `_run_llm_codegen` 成功 `return True` 之前，调用敏感性兜底。具体：把 solver.py:108-111 的成功分支改为先跑兜底再返回：

```python
                if isinstance(metrics, dict) and metrics:
                    success_line = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
                    runs_path.write_text(prior_runs + success_line + "\n", encoding="utf-8")
                    self._llm_script_rel = str(script_path.relative_to(workspace_root))
                    self._run_sensitivity_sweep(workspace_root, processed[0])  # PQ4: backfill if LLM omitted it
                    return True
```

（`_run_sensitivity_sweep` 已自带「存在且≥3 行则不覆盖」的幂等保护，solver.py:431-437，故不会破坏 LLM 真写了 sensitivity 的情况。）

- [ ] **Step 4: 跑测试确认通过** — `pytest tests/test_sensitivity_fallback.py -v` → PASS（全部）
- [ ] **Step 5: 回归** — `pytest tests/test_solver_codegen.py tests/test_sensitivity_fallback.py -q` 全绿
- [ ] **Step 6: 提交**

```bash
git add src/mcm_agent/agents/solver.py tests/test_sensitivity_fallback.py
git commit -m "fix: LLM solver path backfills deterministic sensitivity sweep [PQ4]"
```

---

### Task A2: 默认模型 deepseek-v4-pro + per-role 选模型种子位

**Files:**
- Modify: `src/mcm_agent/config/settings.py`（或定义默认 model 的位置；先用 `grep -rn "deepseek-v4-flash\|default.*model\|MAG_MODEL" src/mcm_agent` 定位）
- Test: `tests/test_settings.py`（或现有 settings 测试文件）

**Interfaces:**
- Produces: `settings` 暴露每角色可选模型的读取（无配置时回退全局 model），不破坏现有单一 model 行为

**说明**：真实 key 在 gitignored `mcm_agent_config.local.json`（开发者本地改 model 即可）。本任务只改**可提交的默认值/读取逻辑**，让「modeler/solver/judge 用更强模型」成为配置可达，而不强制。若现有 settings 无 per-role 概念，**最小实现**：加一个可选 `model_overrides: dict[str, str]`（role->model），`build_llm_provider(settings, role=None)` 优先用 override。**保持 YAGNI**：只加读取与回退，不加 UI。

- [ ] **Step 1: 定位** — `grep -rn "build_llm_provider\|class Settings\|model" src/mcm_agent/config/ src/mcm_agent/providers/llm.py` 找到 model 字段与 provider 构造点
- [ ] **Step 2: 写失败测试** — `test_model_override_falls_back_to_global`：当 `model_overrides={"solver":"deepseek-v4-pro"}` 时 `build_llm_provider(settings, role="solver").model == "deepseek-v4-pro"`，`role="writer"`（无 override）回退全局 model
- [ ] **Step 3: 跑确认失败**
- [ ] **Step 4: 最小实现** — `Settings` 加可选 `model_overrides: dict[str,str] = {}`；`build_llm_provider` 接受可选 `role` 参数，`model = settings.model_overrides.get(role, settings.model)`
- [ ] **Step 5: 跑确认通过 + 回归** — `pytest tests/test_settings.py tests/ -k "provider or settings" -q`
- [ ] **Step 6: 提交**

```bash
git add src/mcm_agent/config/settings.py src/mcm_agent/providers/llm.py tests/test_settings.py
git commit -m "feat: per-role model overrides with global fallback [E1 seed]"
```

> 注：实际把 solver/modeler/judge 接到 `role=` 留到 P1 之后（避免与 Track B 改 solver 冲突）；本任务只铺路。本地默认切 pro 由开发者在 gitignored config 完成（不提交）。

---

## Track B — P1：有状态 Code-Interpreter 求解环（核心）

### Task B1: `CodeInterpreter` 协议 + `ExecResult` + 测试用 fake

**Files:**
- Create: `src/mcm_agent/tools/__init__.py`（空，若不存在）
- Create: `src/mcm_agent/tools/code_interpreter.py`
- Create: `tests/test_code_interpreter.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) ExecResult: stdout: str; error: str; had_error: bool; images: tuple[str, ...] = ()`
  - `class CodeInterpreter(Protocol)`: `add_section(self, title: str) -> None`; `execute(self, code: str) -> ExecResult`; `save_notebook(self) -> None`; `shutdown(self) -> None`
  - 测试用 `FakeCodeInterpreter`（定义在 `tests/test_code_interpreter.py`，供其它测试 import 复用）：构造 `FakeCodeInterpreter(workspace_root)`，`execute` 用持久命名空间 `exec(code, ns)`，cwd 切到 workspace，捕获 stdout、异常→`had_error=True`/`error=traceback`；记录 `self.sections`、`self.executed: list[str]`；`save_notebook` 写一个简单的 `notebook.ipynb`；`shutdown` 无操作。

- [ ] **Step 1: 写失败测试** — `tests/test_code_interpreter.py`：

```python
import io
import contextlib
import traceback
from pathlib import Path

from mcm_agent.tools.code_interpreter import ExecResult, CodeInterpreter


class FakeCodeInterpreter:
    """In-process test double: persistent namespace, real file writes, no kernel."""
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.ns: dict[str, object] = {}
        self.sections: list[str] = []
        self.executed: list[str] = []

    def add_section(self, title: str) -> None:
        self.sections.append(title)

    def execute(self, code: str) -> ExecResult:
        import os
        self.executed.append(code)
        buf = io.StringIO()
        prev = os.getcwd()
        os.chdir(self.workspace_root)
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(code, "<cell>", "exec"), self.ns)  # noqa: S102 (test double)
            return ExecResult(stdout=buf.getvalue(), error="", had_error=False)
        except Exception:
            return ExecResult(stdout=buf.getvalue(), error=traceback.format_exc(), had_error=True)
        finally:
            os.chdir(prev)

    def save_notebook(self) -> None:
        (self.workspace_root / "notebook.ipynb").write_text("{}", encoding="utf-8")

    def shutdown(self) -> None:
        pass


def test_exec_result_fields():
    r = ExecResult(stdout="hi", error="", had_error=False)
    assert r.stdout == "hi" and r.had_error is False and r.images == ()


def test_fake_interpreter_is_stateful_and_writes_files(tmp_path):
    interp = FakeCodeInterpreter(tmp_path)
    interp.add_section("p1")
    interp.execute("x = 41")
    r = interp.execute("print(x + 1)")
    assert "42" in r.stdout and r.had_error is False
    interp.execute("from pathlib import Path; Path('out.txt').write_text('ok')")
    assert (tmp_path / "out.txt").read_text() == "ok"
    err = interp.execute("raise ValueError('boom')")
    assert err.had_error and "boom" in err.error
    # protocol structural check
    assert isinstance(interp, CodeInterpreter)
```

- [ ] **Step 2: 跑确认失败** — `pytest tests/test_code_interpreter.py -v` → FAIL（模块不存在）
- [ ] **Step 3: 实现 `tools/code_interpreter.py`** —（先只放 `ExecResult` + `CodeInterpreter` 协议；`JupyterCodeInterpreter` 在 B1b）：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    error: str
    had_error: bool
    images: tuple[str, ...] = field(default=())


@runtime_checkable
class CodeInterpreter(Protocol):
    def add_section(self, title: str) -> None: ...
    def execute(self, code: str) -> ExecResult: ...
    def save_notebook(self) -> None: ...
    def shutdown(self) -> None: ...
```

- [ ] **Step 4: 跑确认通过** — `pytest tests/test_code_interpreter.py -v` → PASS
- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/tools/__init__.py src/mcm_agent/tools/code_interpreter.py tests/test_code_interpreter.py
git commit -m "feat: CodeInterpreter protocol + ExecResult + in-process test double"
```

---

### Task B1b: `JupyterCodeInterpreter`（持久 kernel 真实现）+ 依赖

**Files:**
- Modify: `pyproject.toml`（dependencies 加 `jupyter_client>=8.6`、`ipykernel>=6.29`、`nbformat>=5.10`）
- Modify: `src/mcm_agent/tools/code_interpreter.py`（加 `JupyterCodeInterpreter`）
- Create: `tests/test_code_interpreter_jupyter_integration.py`（真 kernel；不可用时 `pytest.skip`）

**Interfaces:**
- Produces: `JupyterCodeInterpreter(workspace_root: Path, *, cell_timeout: float = 60.0)`，实现 `CodeInterpreter`；构造时启动 kernel 并跑 setup cell（`os.chdir(workspace)`、`matplotlib.use("Agg")`、best-effort CJK 字体）；构造失败抛异常（调用方据此降级）。`execute` 收集 iopub 直到 `status==idle`，聚合 stdout/`execute_result`/`stream`/`error`，`display_data` 的 png 存到 `figures/` 并记入 `images`；每 cell 追加到内存 notebook。`save_notebook` 用 `nbformat` 写 `workspace/notebook.ipynb`。`shutdown` 关 kernel。

- [ ] **Step 1: 写集成测试**（真 kernel，可跳过）— `tests/test_code_interpreter_jupyter_integration.py`：

```python
import pytest

jupyter_client = pytest.importorskip("jupyter_client")


def _make_interp(tmp_path):
    from mcm_agent.tools.code_interpreter import JupyterCodeInterpreter
    try:
        return JupyterCodeInterpreter(tmp_path, cell_timeout=30.0)
    except Exception as exc:  # no kernel available in this env
        pytest.skip(f"jupyter kernel unavailable: {exc}")


def test_jupyter_state_persists_and_notebook_written(tmp_path):
    interp = _make_interp(tmp_path)
    try:
        interp.add_section("p1")
        interp.execute("a = 20")
        r = interp.execute("print(a * 2 + 2)")
        assert "42" in r.stdout and not r.had_error
        err = interp.execute("1/0")
        assert err.had_error and "ZeroDivisionError" in err.error
        interp.save_notebook()
        assert (tmp_path / "notebook.ipynb").exists()
    finally:
        interp.shutdown()
```

- [ ] **Step 2: 跑确认失败/跳过** — `pytest tests/test_code_interpreter_jupyter_integration.py -v`（类不存在 → FAIL）
- [ ] **Step 3: 加依赖** — `pyproject.toml` dependencies 增三项；`pip install -e .`（或 `uv pip install -e .`）
- [ ] **Step 4: 实现 `JupyterCodeInterpreter`** — 用 `jupyter_client.manager.start_new_kernel` 起 kernel + `KernelClient`；`execute` 通过 `client.execute(code)` 拿 msg_id，循环 `client.get_iopub_msg(timeout=...)` 聚合到 `idle`，超时 → `client.interrupt_kernel()` + `had_error`；`display_data`/`execute_result` 的 `image/png`（base64）解码存 `figures/cell_<n>.png`。notebook 用 `nbformat.v4.new_notebook()`/`new_code_cell`。setup cell 见上。构造失败抛异常。
- [ ] **Step 5: 跑确认通过/跳过** — `pytest tests/test_code_interpreter_jupyter_integration.py -v`（kernel 在则 PASS，不在则 SKIP）
- [ ] **Step 6: 全量回归** — `pytest -q`（确认加依赖未破坏其它）
- [ ] **Step 7: 提交**

```bash
git add pyproject.toml src/mcm_agent/tools/code_interpreter.py tests/test_code_interpreter_jupyter_integration.py
git commit -m "feat: JupyterCodeInterpreter (persistent kernel, ipynb output)"
```

---

### Task B2: `SolverCoderAgent._run_interpreter_loop`（文本协议 ReAct 环）

**Files:**
- Modify: `src/mcm_agent/agents/solver.py`
- Create: `tests/test_solver_interpreter_loop.py`

**Interfaces:**
- Consumes: `CodeInterpreter`（注入）、`llm_provider.generate`、`_model_spec_block`、`_schema_excerpt`、`_read_text`、`read_model_spec`
- Produces: `SolverCoderAgent._run_interpreter_loop(workspace_root, *, interpreter_factory=None, max_turns=12, max_errors=4) -> bool`；成功返回 True 且写出 `results/problem1_results.csv` + `results/model_metrics.json`（非空 dict）+ `notebook.ipynb`；任何构造/执行失败返回 False（调用方降级）。`interpreter_factory: Callable[[Path], CodeInterpreter]`，默认 `JupyterCodeInterpreter`。

**协议**（system prompt 固定）：
```
你在一个【有状态 Python(Jupyter) 会话】里求解 MCM 子问题。变量跨 cell 保留。
要运行代码：只回复**一个** ```python ...``` 代码块，我会执行并把输出/报错回给你。
报错时请基于真实报错修正后重试。
当该子问题**完全解出且所有要求的输出文件已写好**时，只回复一个词 DONE（不带代码块）。
```

**每子问题 prompt**：注入 `MODEL SPEC`（`_model_spec_block`）、数据 schema（`_schema_excerpt`）、CONTRACT（写 `results/problem1_results.csv`、`results/model_metrics.json`〔任务相关键名〕；不要联网/越权）。

**循环**：`transcript = subproblem_prompt`；每轮 `content = generate(system, transcript).content`；`code = _extract_code(content)`（复用 solver.py:122 现成静态方法）；
- 有代码块 → `res = interp.execute(code)` → `transcript += "\n\n[ASSISTANT]\n"+content+"\n\n[CELL OUTPUT]\n"+(res.error if res.had_error else res.stdout)[-2000:]`；`had_error` 累加 error 计数；
- 无代码块（含 DONE）→ 该子问题结束。
- `max_turns`/`max_errors` 封顶。
全部子问题跑完 → `interp.save_notebook()`；校验 `model_metrics.json` 为非空 dict → True，否则 False。`finally: interp.shutdown()`。

- [ ] **Step 1: 写失败测试** — `tests/test_solver_interpreter_loop.py`，用 B1 的 `FakeCodeInterpreter` + 脚本化 LLM：

```python
from pathlib import Path
import pandas as pd
from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.providers.base import ProviderResult
from tests.test_code_interpreter import FakeCodeInterpreter


def _ws(tmp_path):
    (tmp_path / "data" / "processed").mkdir(parents=True)
    pd.DataFrame({"region": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]}).to_csv(
        tmp_path / "data" / "processed" / "d.csv", index=False)
    (tmp_path / "results").mkdir(exist_ok=True)
    (tmp_path / "reports").mkdir(exist_ok=True)
    return tmp_path


class _TwoTurnLLM:
    """Turn 1: emit code that writes the contract outputs. Turn 2: DONE."""
    def __init__(self):
        self.calls = 0
    def generate(self, system, prompt, *, temperature=0.2):
        self.calls += 1
        if self.calls == 1:
            code = (
                "import json, pandas as pd\n"
                "from pathlib import Path\n"
                "df = pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
                "df.to_csv('results/problem1_results.csv', index=False)\n"
                "json.dump({'value_mean': float(df['value'].mean())},"
                " open('results/model_metrics.json','w'))\n"
                "print('metrics written')\n"
            )
            return ProviderResult(content=f"```python\n{code}```", metadata={})
        return ProviderResult(content="DONE", metadata={})


def test_interpreter_loop_writes_outputs_and_notebook(tmp_path):
    ws = _ws(tmp_path)
    agent = SolverCoderAgent(llm_provider=_TwoTurnLLM())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))
    assert ok is True
    assert (ws / "results" / "model_metrics.json").exists()
    assert (ws / "results" / "problem1_results.csv").exists()
    assert (ws / "notebook.ipynb").exists()


def test_interpreter_loop_reflects_on_error_then_succeeds(tmp_path):
    ws = _ws(tmp_path)

    class _ErrThenFix:
        def __init__(self): self.calls = 0
        def generate(self, system, prompt, *, temperature=0.2):
            self.calls += 1
            if self.calls == 1:
                return ProviderResult(content="```python\nraise ValueError('oops')\n```", metadata={})
            if self.calls == 2:
                # transcript must contain the real error we fed back
                assert "ValueError" in prompt and "oops" in prompt
                code = ("import json,pandas as pd\nfrom pathlib import Path\n"
                        "df=pd.read_csv(sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0])\n"
                        "df.to_csv('results/problem1_results.csv',index=False)\n"
                        "json.dump({'value_mean':float(df['value'].mean())},open('results/model_metrics.json','w'))\n")
                return ProviderResult(content=f"```python\n{code}```", metadata={})
            return ProviderResult(content="DONE", metadata={})

    agent = SolverCoderAgent(llm_provider=_ErrThenFix())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))
    assert ok is True
    assert (ws / "results" / "model_metrics.json").exists()


def test_interpreter_loop_returns_false_when_no_metrics(tmp_path):
    ws = _ws(tmp_path)

    class _NeverWrites:
        def generate(self, system, prompt, *, temperature=0.2):
            return ProviderResult(content="DONE", metadata={})

    agent = SolverCoderAgent(llm_provider=_NeverWrites())
    ok = agent._run_interpreter_loop(ws, interpreter_factory=lambda root: FakeCodeInterpreter(root))
    assert ok is False
```

- [ ] **Step 2: 跑确认失败** — `pytest tests/test_solver_interpreter_loop.py -v` → FAIL（方法不存在）
- [ ] **Step 3: 实现 `_run_interpreter_loop`** — 见上「协议/循环」。`interpreter_factory` 默认延迟 import `JupyterCodeInterpreter`（避免无依赖环境 import 失败）：

```python
def _run_interpreter_loop(self, workspace_root, *, interpreter_factory=None,
                          max_turns: int = 12, max_errors: int = 4) -> bool:
    from mcm_agent.core.model_spec import read_model_spec
    processed = sorted((workspace_root / "data" / "processed").glob("*.csv"))
    if not processed:
        return False
    (workspace_root / "results").mkdir(parents=True, exist_ok=True)
    if interpreter_factory is None:
        try:
            from mcm_agent.tools.code_interpreter import JupyterCodeInterpreter
            interpreter_factory = lambda root: JupyterCodeInterpreter(root)
        except Exception:
            return False
    try:
        interp = interpreter_factory(workspace_root)
    except Exception:
        return False
    try:
        spec = read_model_spec(workspace_root)
        subs = spec.subproblems if (spec and spec.subproblems) else [None]
        system = (...)  # 见协议
        for sub in subs:
            interp.add_section(getattr(sub, "title", "problem1"))
            transcript = self._subproblem_prompt(workspace_root, processed[0], sub)
            errors = 0
            for _turn in range(max_turns):
                content = self.llm_provider.generate(system, transcript).content
                code = self._extract_code_block(content)  # 见下
                if not code:
                    break  # DONE / no code
                res = interp.execute(code)
                feedback = (res.error if res.had_error else res.stdout)[-2000:]
                transcript += f"\n\n[ASSISTANT]\n{content}\n\n[CELL OUTPUT]\n{feedback}"
                if res.had_error:
                    errors += 1
                    if errors >= max_errors:
                        break
        interp.save_notebook()
    except Exception:
        try: interp.shutdown()
        except Exception: pass
        return False
    finally:
        try: interp.shutdown()
        except Exception: pass
    metrics = read_json(workspace_root / "results" / "model_metrics.json", {})
    if isinstance(metrics, dict) and metrics:
        self._llm_script_rel = "notebook.ipynb"
        self._run_sensitivity_sweep(workspace_root, processed[0])
        return True
    return False
```

  其中 `_extract_code_block(content)`：返回**仅当**有 ```python ``` 围栏时的代码，否则空串（区别于现有 `_extract_code` 会回退整段文本——ReAct 里「没围栏=DONE」必须靠这个新方法）。`_subproblem_prompt(...)` 复用 `_model_spec_block`/`_schema_excerpt`/`_read_text` 拼 CONTRACT。

- [ ] **Step 4: 跑确认通过** — `pytest tests/test_solver_interpreter_loop.py -v` → PASS（4 例）
- [ ] **Step 5: 回归** — `pytest tests/test_solver_codegen.py tests/test_code_interpreter.py -q`
- [ ] **Step 6: 提交**

```bash
git add src/mcm_agent/agents/solver.py tests/test_solver_interpreter_loop.py
git commit -m "feat: stateful code-interpreter ReAct loop in SolverCoderAgent [P1]"
```

---

### Task B3: 成功路径正确性自评（攻 MMA「只在报错时反思」）

**Files:**
- Modify: `src/mcm_agent/agents/solver.py`（`_run_interpreter_loop` 内）
- Modify: `tests/test_solver_interpreter_loop.py`

**Interfaces:**
- Produces: `SolverCoderAgent._metrics_are_degenerate(metrics: dict) -> tuple[bool, str]`（NaN/inf、全 0、空 → True+原因）。环在某子问题「无代码块=想结束」时，先做确定性自评：若 `model_metrics.json` 缺失或退化且仍有 turn 预算 → 往 transcript 追加一条纠正消息（含退化原因）并**继续**循环，而非结束。

- [ ] **Step 1: 写失败测试** — `test_self_eval_rejects_degenerate_then_continues`：LLM 第 1 轮写出 `{'consistency': 0.0}`（退化）后说 DONE；环应不接受、回灌纠正、第 2 轮写出非退化指标才结束。断言最终 metrics 非退化且 `llm.calls >= 3`。再加 `test_metrics_are_degenerate_unit`（NaN/全 0/空 → True；正常 → False）。
- [ ] **Step 2: 跑确认失败**
- [ ] **Step 3: 实现** — 加 `_metrics_are_degenerate`（用 `math.isfinite`）；在循环里 `if not code:` 分支改为：读 `model_metrics.json`，`degenerate, reason = self._metrics_are_degenerate(metrics)`，若 `degenerate and _turn < max_turns-1`：`transcript += f"\n\n[CHECK FAILED]\n结果退化：{reason}。请修正模型/计算后重写 results/model_metrics.json 与结果表，再继续。"` 并 `continue`；否则 `break`。
- [ ] **Step 4: 跑确认通过 + 回归** — `pytest tests/test_solver_interpreter_loop.py -v`
- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/agents/solver.py tests/test_solver_interpreter_loop.py
git commit -m "feat: success-path correctness self-eval in interpreter loop [B3]"
```

---

### Task B4: 接入 `run()` 降级链 + 输出登记

**Files:**
- Modify: `src/mcm_agent/agents/solver.py`（`run()`）
- Create/Modify: `tests/test_solver_interpreter_loop.py`（run 级测试）

**Interfaces:**
- Produces: `run()` 新降级链：`_run_interpreter_loop` 成功 → `_record_outputs` → return；否则 `_run_llm_codegen` 成功（无 jupyter 时的现有 subprocess 一次性路径）→ `_record_outputs` → return；否则 `_run_templated_baseline`。`_record_outputs` 兼容 `_llm_script_rel="notebook.ipynb"`（已用 `getattr` 默认值，solver.py:139，无需改）。

- [ ] **Step 1: 写失败测试** — `test_run_uses_interpreter_then_records_evidence`：注入成功的 `_TwoTurnLLM` + fake interpreter（通过给 `SolverCoderAgent` 一个可注入的 factory 钩子，或 monkeypatch `_run_interpreter_loop` 用 fake factory），断言 `run()` 后 `results/evidence_registry.json` 含 `metric_value_mean` 项、`results/model_route_summary.json` 存在。`test_run_falls_back_to_baseline_when_interpreter_and_codegen_fail`：`llm_provider=None` → 仍走模板兜底（保持现状绿）。
  - 实现注入：给 `run()` 加可选 `interpreter_factory=None` 参数透传给 `_run_interpreter_loop`（mvp.py 不传 = 用默认 Jupyter）。测试传 fake。
- [ ] **Step 2: 跑确认失败**
- [ ] **Step 3: 实现** — 改 `run()`：

```python
def run(self, workspace_root: Path, *, interpreter_factory=None) -> None:
    if self.llm_provider is not None and self._run_interpreter_loop(
        workspace_root, interpreter_factory=interpreter_factory
    ):
        self._record_outputs(workspace_root)
        return
    if self.llm_provider is not None and self._run_llm_codegen(workspace_root):
        self._record_outputs(workspace_root)
        return
    self._run_templated_baseline(workspace_root)
```

- [ ] **Step 4: 跑确认通过 + 全量回归** — `pytest -q`（**全绿**是硬门）
- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/agents/solver.py tests/test_solver_interpreter_loop.py
git commit -m "feat: wire interpreter loop into solver run() with graceful degrade [P1]"
```

---

### Task B5: 真题 e2e + MockJudge 前后对比（验证，不改产品代码）

**Files:**
- 使用：`scripts/score_paper.py`、真题 workspace（assets/，不提交）
- 记录：`docs/superpowers/specs/2026-06-19-mag-real-paper-engine-design.md` 或 memory `project_real_paper_engine.md` 追加新基线

- [ ] **Step 1:** 在装有 jupyter + 真实 deepseek-v4-pro 的环境跑一遍 MCM-C 真题完整流水线（`mag` 真壳或 `run_once` 触发），确认 `notebook.ipynb` 产出、`results/model_metrics.json` 非退化、敏感性 ≥3 行、PDF 编译且含图。
- [ ] **Step 2:** `python scripts/score_paper.py <ws>` 记录 10 维分；与切换前基线（~4.7）对比，重点看 `data_solution`/`mathematics`/`validation`/`sensitivity`。
- [ ] **Step 3:** 把新基线 + notebook 路径 + 分数写进 memory `project_real_paper_engine.md`（晨间可复核）。**不提交 assets/**。
- [ ] **Step 4:** 提交文档更新（仅 docs/memory 指针）。

---

## Self-Review（计划自检）

- **Spec coverage**：P1（CI 环）= B1/B1b/B2/B4；B3 = 成功路径自评；PQ4 收尾 = A1；模型 = A2；验证 = B5。覆盖了用户拍板的「P0 收尾 + P1 并行」。O6/多模态/检索属 P2/P3，**本计划不含**（按「先改进，看过再议」收敛范围）。
- **Placeholder scan**：每个代码步给了真实代码/真实断言，无 TODO 占位。
- **Type consistency**：`ExecResult`、`CodeInterpreter`、`_run_interpreter_loop(... )->bool`、`run(..., interpreter_factory=None)`、`_extract_code_block`、`_metrics_are_degenerate` 在引用处签名一致。`_extract_code`（现存，会回退整段）与新 `_extract_code_block`（仅围栏）刻意区分，已在 B2 注明。
- **降级链**：interpreter → 一次性 codegen → 模板，三层都有测试覆盖其一，headless/无 jupyter 安全。

## Execution Handoff
建议 **Subagent-Driven**：每任务 实现(TDD)→复审→修→提交；按 Track A→B 顺序（A1/A2 可并行于 B 系列，但都改 solver.py，故 **A1 先落地再开 B 系列**避免冲突）。每组 `git push origin main`。
