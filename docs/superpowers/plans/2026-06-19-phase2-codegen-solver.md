# Phase 2: 会写代码的求解 agent + 论文装配修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Mag 为真题生成**题目专属**的真实建模结果（而非套罐头 TOPSIS），并让论文 Results/摘要/引用反映真实结果——使 MCM C 论文内容对题。

**Architecture:** `SolverCoderAgent` 增加 LLM 代码生成路径：基于研究脚本 + 数据 schema，让 LLM 写题目专属 Python，经现有 `run_experiment` 子进程执行，失败把 traceback 回喂 LLM 自修复（有限次），全失败回退现有罐头 baseline。LLM 脚本产出的 `results/model_metrics.json` 沿用现有 evidence→claim→论文链路，真实指标自动进入 Results。另修复摘要倒原文与引用刷屏。

**Tech Stack:** Python 3.12、现有 `mcm_agent` agents/providers、`core/experiment.py::run_experiment`、pandas/numpy/scipy/sklearn、pytest、ruff。

**对应 spec:** `docs/superpowers/specs/2026-06-19-mag-real-paper-engine-design.md`（§6 内核 C + §5.4 论文装配 D）。

---

## 背景事实（已核查）

- `solver_coder` stage（`workflows/mvp.py:308`）当前 `SolverCoderAgent().run(workspace_root)`，**未传 LLM**。
- 输出契约：脚本须写 `results/problem1_results.csv` 与 `results/model_metrics.json`（dict）。`SolverCoderAgent.run` 之后把 `model_metrics.json` 每个键记成 `EvidenceItem(metric_<key>)`，写 `model_route_summary.json`，下游 claim_planning→writer 据此生成 Results。
- 执行 harness：`run_experiment(workspace_root, ["python", script_rel], produced_files=[...], timeout_seconds=...)` 返回 `exit_code`/`missing_outputs`/`stdout_path`/`stderr_path`。
- Agent LLM 范式：`__init__(self, llm_provider=None)` + 构造 prompt + `self.llm_provider.generate(system, prompt)`；解析用 `re` 提取围栏代码块。
- 摘要 bug：`agents/paper_context.py::_summarize_markdown` 取 `problem_understanding.md` 前 500 字符塞进 `agents/paper_sections.py::_render_abstract` → 倒原文。
- 引用刷屏：claim plan 每条 claim 的 `source_ids` 含全部来源 → `citations.cite_command` 全列出。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `src/mcm_agent/workflows/mvp.py` | solver_coder stage 传入 `provider_bundle.llm` | 修改 |
| `src/mcm_agent/agents/solver.py` | LLM 代码生成路径 + 自修复 + 回退 baseline | 修改 |
| `src/mcm_agent/agents/paper_context.py` | 摘要用题目摘要而非原文倒灌 | 修改 |
| `src/mcm_agent/agents/claim_planning.py` | 每条 claim 只挂相关来源（收敛引用） | 修改 |
| `tests/test_solver_codegen.py` | LLM 脚本生成/执行/自修复/回退 | 新建 |
| `tests/test_solver_evidence.py` | 现有 baseline 行为不退化 | 复用/必要时改 |
| `tests/test_paper_context.py` | 摘要不倒原文 | 修改 |
| `tests/test_claim_planning.py` | 引用收敛 | 修改 |

每个 Task：`pytest -q` + `ruff` 绿 → commit → push main。

---

## Task 1: solver_coder stage 传入 LLM；SolverCoderAgent 接受可选 llm_provider

**Files:**
- Modify: `src/mcm_agent/workflows/mvp.py`
- Modify: `src/mcm_agent/agents/solver.py`
- Test: `tests/test_solver_evidence.py`（确保现有 baseline 不退化）

- [ ] **Step 1: 改 `SolverCoderAgent.__init__` 接受可选 provider（默认 None → 走 baseline）**

```python
class SolverCoderAgent:
    def __init__(self, llm_provider: object | None = None) -> None:
        self.llm_provider = llm_provider
```

把现有 `run` 的模板生成主体抽成 `_run_templated_baseline(self, workspace_root) -> None`（原 run 体原样移入），新的 `run` 暂时仍只调 baseline：

```python
    def run(self, workspace_root: Path) -> None:
        self._run_templated_baseline(workspace_root)
```

- [ ] **Step 2: 运行现有 solver 测试，确认不退化**

Run: `pytest tests/test_solver_evidence.py tests/test_solver_modules.py -q`
Expected: PASS（行为等价，仅重构）。

- [ ] **Step 3: stage 传入 LLM**

`workflows/mvp.py:309` 改为：

```python
        SolverCoderAgent(provider_bundle.llm).run(workspace_root)
```

- [ ] **Step 4: 全量回归**

Run: `pytest tests/test_mvp_workflow.py tests/test_solver_evidence.py -q`
Expected: PASS（fake LLM 下仍走 baseline）。

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/agents/solver.py src/mcm_agent/workflows/mvp.py
git commit -m "refactor: SolverCoderAgent accepts llm provider; extract templated baseline"
```

---

## Task 2: LLM 代码生成 + 执行 + 自修复（核心）

**Files:**
- Modify: `src/mcm_agent/agents/solver.py`
- Test: `tests/test_solver_codegen.py`

设计：新增 `_run_llm_codegen(workspace_root) -> bool`，成功返回 True 并已写出 `results/problem1_results.csv` + `results/model_metrics.json`。`run` 改为：

```python
    def run(self, workspace_root: Path) -> None:
        if self.llm_provider is not None and self._run_llm_codegen(workspace_root):
            self._record_outputs(workspace_root)  # 见 Step 4
            return
        self._run_templated_baseline(workspace_root)
```

代码契约（写入 prompt）：脚本必须 `import pandas`，从 `input/data/` 或 `data/processed/` 读数据；把题目专属指标写入 `results/model_metrics.json`（dict，键名体现题目，如 `elimination_consistency_rate`）；把主结果写 `results/problem1_results.csv`；只用 pandas/numpy/scipy/sklearn/matplotlib。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_solver_codegen.py`：

```python
from pathlib import Path

from mcm_agent.agents.solver import SolverCoderAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.utils.json_io import read_json


class _ScriptLLM:
    """Fake LLM returning a fixed python script in a fenced block."""

    def __init__(self, script: str, *, fail_first: bool = False):
        self.script = script
        self.fail_first = fail_first
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        body = self.script
        if self.fail_first and self.calls == 1:
            body = "import sys\nraise SystemExit('boom')\n"
        return f"```python\n{body}\n```"


GOOD_SCRIPT = """
import json
from pathlib import Path
import pandas as pd
ws = Path.cwd()
df = pd.read_csv(sorted((ws / 'data' / 'processed').glob('*.csv'))[0])
df['estimate'] = 1.0
df.to_csv(ws / 'results' / 'problem1_results.csv', index=False)
(ws / 'results' / 'model_metrics.json').write_text(
    json.dumps({'elimination_consistency_rate': 0.91, 'rows': int(len(df))}), encoding='utf-8')
"""


def _prepare(tmp_path: Path) -> Path:
    root = create_workspace(tmp_path / "ws").root
    (root / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (root / "data" / "processed" / "data.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    (root / "reports" / "problem_understanding.md").write_text("# understanding\nestimate votes", encoding="utf-8")
    return root


def test_llm_codegen_produces_task_metrics(tmp_path: Path) -> None:
    root = _prepare(tmp_path)
    SolverCoderAgent(_ScriptLLM(GOOD_SCRIPT)).run(root)
    metrics = read_json(root / "results" / "model_metrics.json", {})
    assert metrics.get("elimination_consistency_rate") == 0.91
    evidence = read_json(root / "results" / "evidence_registry.json", [])
    assert any(e.get("evidence_id") == "metric_elimination_consistency_rate" for e in evidence)


def test_llm_codegen_self_repairs_then_succeeds(tmp_path: Path) -> None:
    root = _prepare(tmp_path)
    llm = _ScriptLLM(GOOD_SCRIPT, fail_first=True)
    SolverCoderAgent(llm).run(root)
    assert llm.calls >= 2  # repaired after first failure
    metrics = read_json(root / "results" / "model_metrics.json", {})
    assert metrics.get("elimination_consistency_rate") == 0.91


def test_llm_codegen_falls_back_to_baseline_when_unfixable(tmp_path: Path) -> None:
    root = _prepare(tmp_path)

    class _AlwaysBad:
        def generate(self, system: str, prompt: str) -> str:
            return "```python\nraise SystemExit('always')\n```"

    SolverCoderAgent(_AlwaysBad()).run(root)
    # baseline still produced the standard outputs
    assert (root / "results" / "problem1_results.csv").exists()
    assert (root / "results" / "model_metrics.json").exists()
```

> 注：baseline 读 `data/processed/*.csv`；LLM 脚本契约同样读该目录，测试已 prepare 该文件。

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_solver_codegen.py -q`
Expected: FAIL（`_run_llm_codegen` 未实现）。

- [ ] **Step 3: 实现 `_run_llm_codegen` + `_record_outputs`**

在 `solver.py` 增加（核心方法；`run_experiment`、`read_json`、`write_json`、`EvidenceItem` 已 import）：

```python
import re

    def _run_llm_codegen(self, workspace_root: Path, *, max_attempts: int = 3) -> bool:
        processed = sorted((workspace_root / "data" / "processed").glob("*.csv"))
        if not processed:
            return False
        understanding = self._read_text(workspace_root / "reports" / "problem_understanding.md", 4000)
        direction = self._read_text(workspace_root / "discussion" / "confirmed_direction.md", 1500)
        schema = self._schema_excerpt(processed[0])
        code_dir = workspace_root / "code" / "experiments"
        code_dir.mkdir(parents=True, exist_ok=True)
        script_path = code_dir / "problem1.py"
        system = "You write correct, self-contained Python for a math-modeling contest. Output ONLY one ```python code block."
        base_prompt = (
            "Write a Python script that solves the contest sub-problems using the real data.\n"
            f"PROBLEM UNDERSTANDING:\n{understanding}\n\nCONFIRMED DIRECTION:\n{direction}\n\n"
            f"DATA SCHEMA (first rows):\n{schema}\n\n"
            "CONTRACT:\n"
            "- import pandas as pd; read data via sorted((Path.cwd()/'data'/'processed').glob('*.csv'))[0]\n"
            "- Use only pandas, numpy, scipy, sklearn, matplotlib.\n"
            "- Write the main result table to results/problem1_results.csv\n"
            "- Write a JSON dict of TASK-SPECIFIC metrics (keys named after the problem, e.g. "
            "elimination_consistency_rate) to results/model_metrics.json\n"
            "- Do not call network or read files outside the workspace.\n"
        )
        last_err = ""
        for attempt in range(max_attempts):
            prompt = base_prompt if attempt == 0 else (
                base_prompt + f"\n\nThe previous script failed with:\n{last_err}\nFix it and return the full corrected script."
            )
            code = self._extract_code(self.llm_provider.generate(system, prompt))
            if not code:
                return False
            script_path.write_text(code, encoding="utf-8")
            record = run_experiment(
                workspace_root,
                ["python", str(script_path.relative_to(workspace_root))],
                produced_files=["results/problem1_results.csv", "results/model_metrics.json"],
                timeout_seconds=180,
            )
            if record.exit_code == 0 and not record.missing_outputs:
                metrics = read_json(workspace_root / "results" / "model_metrics.json", {})
                if isinstance(metrics, dict) and metrics:
                    self._llm_script_rel = str(script_path.relative_to(workspace_root))
                    return True
                last_err = "model_metrics.json missing or empty dict"
            else:
                stderr_path = workspace_root / record.stderr_path
                last_err = stderr_path.read_text(encoding="utf-8")[-1500:] if stderr_path.exists() else "missing outputs"
        return False

    @staticmethod
    def _extract_code(text: str) -> str:
        match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
        return (match.group(1) if match else text).strip()

    @staticmethod
    def _read_text(path: Path, limit: int) -> str:
        return path.read_text(encoding="utf-8")[:limit] if path.exists() else ""

    @staticmethod
    def _schema_excerpt(csv_path: Path) -> str:
        import pandas as pd
        df = pd.read_csv(csv_path, nrows=5)
        return f"columns={list(df.columns)}\n{df.to_string(index=False)}"

    def _record_outputs(self, workspace_root: Path) -> None:
        results_dir = workspace_root / "results"
        metrics = read_json(results_dir / "model_metrics.json", {})
        write_json(
            results_dir / "model_route_summary.json",
            {
                "selected_routes": ["llm_generated"],
                "route_metrics": {},
                "source_result": "results/problem1_results.csv",
                "generated_by": getattr(self, "_llm_script_rel", "code/experiments/problem1.py"),
            },
        )
        lineage_ids = self._lineage_ids_for_processed_file(
            workspace_root, sorted((workspace_root / "data" / "processed").glob("*.csv"))[0]
        )
        evidence = read_json(results_dir / "evidence_registry.json", [])
        for key, value in (metrics.items() if isinstance(metrics, dict) else []):
            if not isinstance(value, (int, float, str)):
                continue
            evidence.append(
                EvidenceItem(
                    evidence_id=f"metric_{key}",
                    claim=f"Metric {key} equals {value}.",
                    value=value,
                    source_type="code_output",
                    source_path="results/model_metrics.json",
                    generated_by=getattr(self, "_llm_script_rel", "code/experiments/problem1.py"),
                    used_in=[],
                    verified=True,
                    lineage_ids=lineage_ids,
                ).model_dump(mode="json")
            )
        write_json(results_dir / "evidence_registry.json", evidence)
        Coordinator(workspace_root).emit("code.completed", source="SolverCoderAgent")
```

并把 `run` 改为先试 LLM、再回退（见任务开头）。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_solver_codegen.py -q`
Expected: PASS（3 个用例）。

- [ ] **Step 5: 全量回归 + ruff**

Run: `pytest tests/test_solver_evidence.py tests/test_mvp_workflow.py -q && ruff check src/mcm_agent/agents/solver.py tests/test_solver_codegen.py`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/mcm_agent/agents/solver.py tests/test_solver_codegen.py
git commit -m "feat: LLM-generated problem-specific solver with self-repair and baseline fallback"
```

---

## Task 3: 摘要不再倒灌题意理解原文

**Files:**
- Modify: `src/mcm_agent/agents/paper_context.py`
- Test: `tests/test_paper_context.py`

问题：`_summarize_markdown` 取报告前 500 字符当 `problem_summary`，摘要直接拼接，导致倒灌。修复：`problem_summary` 取报告中"## 题目背景/Background"段首句（或首个非标题段落首句），并硬限制长度（≤200 字符）。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_paper_context.py`）

```python
def test_problem_summary_is_short_and_not_raw_dump(tmp_path):
    from mcm_agent.agents.paper_context import build_paper_context
    from mcm_agent.core.workspace import create_workspace
    root = create_workspace(tmp_path / "ws").root
    (root / "reports" / "problem_understanding.md").write_text(
        "# 题意理解报告\n## 题目背景\n本题研究 DWTS 投票公平性。\n## 子问题拆解\n" + "细节 " * 400,
        encoding="utf-8",
    )
    ctx = build_paper_context(root)
    assert len(ctx.problem_summary) <= 200
    assert "子问题拆解" not in ctx.problem_summary
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_paper_context.py::test_problem_summary_is_short_and_not_raw_dump -q`
Expected: FAIL（当前 500 字符且含后续章节）。

- [ ] **Step 3: 实现**

在 `paper_context.py` 新增 `_summarize_problem`（取"题目背景/Background"段或首段首句，≤200），并把 `problem_summary=` 改用它：

```python
def _summarize_problem(path: Path, *, max_chars: int = 200) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    paragraph: list[str] = []
    in_background = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if paragraph:
                break
            in_background = ("背景" in stripped) or ("background" in stripped.lower())
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if in_background or not paragraph:
            paragraph.append(stripped)
    text = " ".join(paragraph).strip()
    sentence = re.split(r"(?<=[。.!?])\s*", text)[0] if text else ""
    return sentence[:max_chars] if sentence else text[:max_chars]
```

`build_paper_context` 中 `problem_summary=_summarize_markdown(...)` 改为 `problem_summary=_summarize_problem(workspace_root / "reports" / "problem_understanding.md")`。文件顶部 `import re`。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `pytest tests/test_paper_context.py tests/test_paper_evidence_binding.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/agents/paper_context.py tests/test_paper_context.py
git commit -m "fix: abstract uses a short problem summary instead of dumping the raw report"
```

---

## Task 4: 引用收敛（每条 claim 不再刷全部来源）

**Files:**
- Modify: `src/mcm_agent/agents/claim_planning.py`
- Test: `tests/test_claim_planning.py`

问题：claim plan 给每条 claim 挂全部 `source_ids`。修复：每条 claim 最多挂前 N（如 3）个最相关来源（先按已有相关性排序，否则取前 N）。

- [ ] **Step 1: 定位** claim 的 `source_ids` 赋值处（`grep -n "source_ids" src/mcm_agent/agents/claim_planning.py`）。

- [ ] **Step 2: 写失败测试**（追加到 `tests/test_claim_planning.py`，构造 >3 来源场景，断言生成的 claim_plan 中任一 critical claim 的 `source_ids` 长度 ≤3）。

- [ ] **Step 3: 实现**：在赋值处对来源列表切片 `[:3]`（保持去重、保留顺序）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `pytest tests/test_claim_planning.py tests/test_paper_evidence_binding.py -q`

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/agents/claim_planning.py tests/test_claim_planning.py
git commit -m "fix: cap citations per claim to most-relevant sources (no citation spam)"
```

---

## Task 5: Phase 2 真题回归（MCM C）

- [ ] **Step 1: 全量回归**：`pytest -q && ruff check src tests scripts` 全绿。
- [ ] **Step 2: 真跑**：
```bash
python scripts/real_smoke.py \
  --problem assets/diagnostic_2026_mcm_c/problem.md \
  --data assets/diagnostic_2026_mcm_c/2026_MCM_Problem_C_Data.csv --fast
```
Expected: `WORKFLOW COMPLETED`；`results/model_metrics.json` 含题目专属键（如淘汰一致性），而非仅 `numeric_mean`；PDF 非空。
- [ ] **Step 3: 人工抽检** `results/model_metrics.json` 与 PDF 的 Results：确认报告的是 fan-vote / 淘汰一致性 / rank-vs-percent 等真实结果。记录 Phase 3（对话式 CLI）待办。
- [ ] **Step 4: 提交**（如有文档更新）。

---

## Self-Review 检查

- **Spec 覆盖**：内核 C（T1+T2）、摘要 D（T3）、引用 D（T4）、真题验收（T5）。
- **类型一致**：`SolverCoderAgent.__init__(llm_provider=None)`；`_run_llm_codegen(workspace_root, max_attempts) -> bool`；`_record_outputs(workspace_root)`；`run` 先 LLM 后 baseline。
- **风险**：LLM 代码不稳定 → 自修复 ≤3 + baseline 兜底 + 子进程 180s 超时 + 受限库（prompt 约束，非强沙箱；Phase 3 可加强）。LLM 脚本读 `data/processed`（与 baseline 一致，EDA 阶段已产出）。
- **无占位符**：核心方法含完整代码；T4 需先 grep 定位赋值处（已在 Step 1 说明命令）。
