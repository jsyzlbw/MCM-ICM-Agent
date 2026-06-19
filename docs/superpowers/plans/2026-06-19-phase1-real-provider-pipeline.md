# Phase 1: 真实 Provider 端到端管道 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `mag` 在真实 provider（DeepSeek LLM + tectonic LaTeX 等）下，从导入题目跑到可编译的 PDF，不崩溃、不中文丢字。

**Architecture:** 不改 workflow 拓扑。补齐四条接缝：(1) CLI 配置真正写全 LLM provider/base_url/model；(2) `WorkspaceWorkflowAdapter` 加载 workspace 配置并构建真实 provider bundle 传入 `run_mvp_workflow`；(3) 可选 provider（humanizer）失败降级而非崩溃；(4) `LatexProvider` 支持 tectonic，论文导言区按是否含 CJK 切换。

**Tech Stack:** Python 3.12、Typer、pydantic-settings、httpx、tectonic、pytest、ruff、现有 `mcm_agent` 模块。

**对应 spec:** `docs/superpowers/specs/2026-06-19-mag-real-paper-engine-design.md`（§5，缺陷 A/E/F + Task1 配置缺陷）。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `src/mcm_agent/cli_commands/init.py` | `/init` 写全 LLM key+base_url+model 到 `.env` | 修改 |
| `src/mcm_agent/core/workflow_adapter.py` | 加载 workspace 配置、构建真实 bundle、传入 workflow | 修改 |
| `src/mcm_agent/agents/compliance.py` | humanizer 失败逐段降级，不崩 | 修改 |
| `src/mcm_agent/providers/latex.py` | 命令探测（tectonic→latexmk→xelatex）+ 正确调用 | 修改 |
| `src/mcm_agent/agents/writer.py` | `_write_main_files` 按 CJK 切换导言区 | 修改 |
| `scripts/real_smoke.py` | 开发期真 provider smoke（默认不进 CI） | 新建 |
| `tests/test_init_command.py` | `/init` 写全 LLM 配置 | 修改 |
| `tests/test_workflow_adapter.py` | adapter 构建真实 provider bundle | 修改 |
| `tests/test_compliance_resilience.py` | humanizer 失败不崩 | 新建 |
| `tests/test_latex.py` | tectonic 命令探测与调用 | 修改 |
| `tests/test_paper_cjk_preamble.py` | CJK 导言区切换 | 新建 |

每个 Task 完成标准：`pytest -q` 与 `ruff check src tests` 全绿，单独 commit 并 push `main`。

---

## Task 1: `/init` 写全 LLM provider 配置

**问题：** `init.py::_write_llm_key` 只写 `MAG_LLM_API_KEY`，不写 base_url/model；用户配 DeepSeek 会被打到 `api.openai.com`、用错 model。`config.py` 已支持读取 `MAG_LLM_BASE_URL`/`MAG_LLM_MODEL`。

**Files:**
- Modify: `src/mcm_agent/cli_commands/init.py`
- Test: `tests/test_init_command.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_init_command.py` 末尾追加：

```python
def test_init_writes_full_llm_config(tmp_path):
    from mcm_agent.cli_commands.init import InitCommand
    from mcm_agent.cli_commands.base import CommandContext
    from mcm_agent.core.workspace import create_workspace

    root = create_workspace(tmp_path / "ws").root
    InitCommand().run(
        ["--llm-key", "sk-deepseek", "--llm-base-url", "https://api.deepseek.com/v1", "--llm-model", "deepseek-v4-flash"],
        CommandContext(workspace_root=root),
    )
    env_text = (root / ".env").read_text(encoding="utf-8")
    assert "MAG_LLM_API_KEY=sk-deepseek" in env_text
    assert "MAG_LLM_BASE_URL=https://api.deepseek.com/v1" in env_text
    assert "MAG_LLM_MODEL=deepseek-v4-flash" in env_text
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_init_command.py::test_init_writes_full_llm_config -v`
Expected: FAIL（base_url/model 未写入）。

- [ ] **Step 3: 实现**

在 `init.py` 的 `run` 中解析新选项，并扩展写入函数。把 `_write_llm_key` 替换为：

```python
    def run(self, args: list[str], context: CommandContext) -> CommandResult:
        root = Path(context.workspace_root)
        # ... 既有 rethink/full-reset 分支保持不变 ...
        llm_key = self._extract_option(args, "--llm-key")
        if not llm_key:
            return CommandResult("LLM API 尚未配置。Usage: /init --llm-key <key> [--llm-base-url <url>] [--llm-model <model>]")
        base_url = self._extract_option(args, "--llm-base-url")
        model = self._extract_option(args, "--llm-model")
        self._write_llm_config(root, llm_key, base_url, model)
        # ... 既有后续逻辑保持不变 ...
```

新增方法（替换原 `_write_llm_key`）：

```python
    def _write_llm_config(self, root: Path, key: str, base_url: str | None, model: str | None) -> None:
        env_path = root / ".env"
        existing = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        managed = {"MAG_LLM_API_KEY", "MAG_LLM_BASE_URL", "MAG_LLM_MODEL"}
        lines = [line for line in existing if line.split("=", 1)[0] not in managed]
        lines.append(f"MAG_LLM_API_KEY={key}")
        if base_url:
            lines.append(f"MAG_LLM_BASE_URL={base_url}")
        if model:
            lines.append(f"MAG_LLM_MODEL={model}")
        env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
```

> 注意：保留原 `run` 中除 LLM 写入外的所有既有逻辑（state 更新、checkpoint、返回信息）。只替换 key 写入这一段。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `pytest tests/test_init_command.py -v`
Expected: 全部 PASS（含原有用例）。

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/cli_commands/init.py tests/test_init_command.py
git commit -m "feat: /init persists llm base_url and model"
```

---

## Task 2: Adapter 构建并传入真实 provider bundle

**问题：** `WorkspaceWorkflowAdapter.run_default_workflow` 调 `run_mvp_workflow` 不传 providers/settings → 永远 fake。

**Files:**
- Modify: `src/mcm_agent/core/workflow_adapter.py`
- Test: `tests/test_workflow_adapter.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_workflow_adapter.py` 顶部 import 处补充并追加测试：

```python
from mcm_agent.providers.llm import OpenAICompatibleLLMProvider, FakeLLMProvider


def test_adapter_builds_real_llm_from_workspace_config(tmp_path):
    root = _workspace_with_inputs(tmp_path)
    env = root / ".env"
    env.write_text(
        "MAG_LLM_API_KEY=sk-x\nMAG_LLM_BASE_URL=https://api.deepseek.com/v1\nMAG_LLM_MODEL=deepseek-v4-flash\n",
        encoding="utf-8",
    )
    settings, bundle = WorkspaceWorkflowAdapter(root).build_providers()
    assert isinstance(bundle.llm, OpenAICompatibleLLMProvider)
    assert bundle.llm.base_url == "https://api.deepseek.com/v1"
    assert settings.openai_model == "deepseek-v4-flash"


def test_adapter_falls_back_to_fake_without_key(tmp_path):
    root = _workspace_with_inputs(tmp_path)
    # _workspace_with_inputs 用 /init --llm-key test-key 写了 key；清掉以验证回退
    (root / ".env").write_text("", encoding="utf-8")
    _settings, bundle = WorkspaceWorkflowAdapter(root).build_providers()
    assert isinstance(bundle.llm, FakeLLMProvider)
```

> 确认 `OpenAICompatibleLLMProvider` 暴露 `base_url` 属性（providers/llm.py 第 31 行 `self.base_url = ...`，已存在）。

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_workflow_adapter.py::test_adapter_builds_real_llm_from_workspace_config -v`
Expected: FAIL（`build_providers` 不存在）。

- [ ] **Step 3: 实现**

修改 `src/mcm_agent/core/workflow_adapter.py`，顶部 import：

```python
from mcm_agent.config import load_settings, Settings
from mcm_agent.providers.base import ProviderBundle
from mcm_agent.providers.factory import build_provider_bundle
```

新增方法并改写 `run_default_workflow`：

```python
    def build_providers(self) -> tuple[Settings, ProviderBundle]:
        settings = load_settings(workspace_root=self.root)
        bundle = build_provider_bundle(settings, workspace_root=self.root)
        return settings, bundle

    def run_default_workflow(self, *, auto_approve: bool = True) -> None:
        settings, providers = self.build_providers()
        run_mvp_workflow(
            self.root,
            self.to_task_input(),
            providers=providers,
            settings=settings,
            auto_approve=auto_approve,
        )
        self.sync_outputs()
        WorkspaceSafety(self.root).checkpoint("mag: run workflow")
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `pytest tests/test_workflow_adapter.py -v`
Expected: 全部 PASS（含原有 `test_start_lock_run_executes_fake_workflow`，因无 key 时回退 fake）。

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/core/workflow_adapter.py tests/test_workflow_adapter.py
git commit -m "feat: workflow adapter wires real providers from workspace config"
```

---

## Task 3: humanizer 失败逐段降级（可选 provider 不致命）

**问题：** `ComplianceOriginalityAgent.run` 中 `self.humanizer_provider.humanize(...)` 抛异常（真跑 UShallPass 返回 400）会中断整个 workflow。humanizer 是可选 provider。

**Files:**
- Modify: `src/mcm_agent/agents/compliance.py`
- Test: `tests/test_compliance_resilience.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_compliance_resilience.py`：

```python
from pathlib import Path

from mcm_agent.agents.compliance import ComplianceOriginalityAgent
from mcm_agent.core.workspace import create_workspace


class _BoomHumanizer:
    def humanize(self, text: str, *, language: str = "en") -> str:
        raise RuntimeError("UShallPass submit failed: 400")


def test_compliance_survives_humanizer_failure(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    section_dir = root / "paper" / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    original = "\\section{Model}\nThe model estimates fan votes from judge scores.\n"
    (section_dir / "model.tex").write_text(original, encoding="utf-8")

    ComplianceOriginalityAgent(_BoomHumanizer()).run(root)

    # 不抛异常，且原文保留
    assert (section_dir / "model.tex").read_text(encoding="utf-8") == original
    report = (root / "review" / "originality_report.md").read_text(encoding="utf-8")
    assert "humaniz" in report.lower()
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_compliance_resilience.py -v`
Expected: FAIL（`RuntimeError` 冒泡）。

- [ ] **Step 3: 实现**

在 `compliance.py` 的逐段循环里包裹 humanize 调用，并记录降级。把第 28-29 行附近：

```python
                before_locks = extract_fact_locks(paragraph)
                candidate = self.humanizer_provider.humanize(paragraph, language="en")
                after_locks = extract_fact_locks(candidate)
```

改为：

```python
                before_locks = extract_fact_locks(paragraph)
                try:
                    candidate = self.humanizer_provider.humanize(paragraph, language="en")
                except Exception as exc:  # 可选 provider，失败降级保留原文
                    candidate = paragraph
                    if "- Humanizer unavailable" not in "\n".join(originality_lines):
                        originality_lines.append(
                            f"- Humanizer unavailable; kept original text. Reason: {type(exc).__name__}."
                        )
                after_locks = extract_fact_locks(candidate)
```

> `originality_lines` 已在方法开头定义（第 18 行）。降级提示只追加一次。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_compliance_resilience.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/agents/compliance.py tests/test_compliance_resilience.py
git commit -m "fix: humanizer failure degrades gracefully instead of crashing workflow"
```

---

## Task 4: `LatexProvider` 支持 tectonic（命令探测）

**问题：** `LatexProvider` 写死 `latexmk`（本机未装），但有 `tectonic`。tectonic 调用语义是 `tectonic main.tex`，与 latexmk 参数不同。现有测试 `test_latex_provider_returns_blocked_result_when_latexmk_missing` 用显式缺失命令，需同步更新。

**Files:**
- Modify: `src/mcm_agent/providers/latex.py`
- Test: `tests/test_latex.py`

- [ ] **Step 1: 改写/新增测试**

把 `tests/test_latex.py` 中 `test_latex_provider_returns_blocked_result_when_latexmk_missing` 替换为以下两个测试：

```python
def test_latex_provider_blocked_when_forced_command_missing(tmp_path):
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}")

    result = LatexProvider(command="definitely-missing-engine").compile(paper_dir)

    assert result.success is False
    assert "definitely-missing-engine" in result.reason
    assert (paper_dir / "compile_log.txt").exists()


def test_latex_provider_blocked_when_no_engine_available(tmp_path, monkeypatch):
    import mcm_agent.providers.latex as latex_mod
    monkeypatch.setattr(latex_mod.shutil, "which", lambda name: None)
    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}")

    result = LatexProvider().compile(paper_dir)

    assert result.success is False
    assert "no latex engine" in result.reason.lower()
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_latex.py -v`
Expected: 新测试 FAIL（默认 `command="latexmk"`，无探测逻辑）。

- [ ] **Step 3: 实现**

把 `src/mcm_agent/providers/latex.py` 的 `LatexProvider` 改为：

```python
class LatexProvider:
    # 探测优先级：tectonic（单二进制、自动取字体）> latexmk > xelatex
    _ENGINES = ["tectonic", "latexmk", "xelatex"]

    def __init__(self, command: str | None = None) -> None:
        self.command = command  # None = 自动探测

    def _resolve_command(self) -> str | None:
        if self.command is not None:
            return self.command if shutil.which(self.command) else None
        for engine in self._ENGINES:
            if shutil.which(engine):
                return engine
        return None

    def _invocation(self, engine: str) -> list[str]:
        name = Path(engine).name
        if name == "tectonic":
            return [engine, "main.tex"]
        if name == "latexmk":
            return [engine, "-pdf", "-interaction=nonstopmode", "main.tex"]
        # xelatex / pdflatex 等
        return [engine, "-interaction=nonstopmode", "main.tex"]

    def compile(self, paper_dir: Path) -> LatexCompileResult:
        log_path = paper_dir / "compile_log.txt"
        engine = self._resolve_command()
        if engine is None:
            if self.command is not None:
                reason = f"{self.command} not available"
            else:
                reason = "no latex engine available (install tectonic or latexmk)"
            log_path.write_text(reason + "\n", encoding="utf-8")
            return LatexCompileResult(success=False, log_path=str(log_path), reason=reason)

        result = subprocess.run(
            self._invocation(engine),
            cwd=paper_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        pdf_path = paper_dir / "main.pdf"
        return LatexCompileResult(
            success=result.returncode == 0 and pdf_path.exists(),
            pdf_path=str(pdf_path) if pdf_path.exists() else None,
            log_path=str(log_path),
            reason="" if result.returncode == 0 and pdf_path.exists() else f"{Path(engine).name} failed: {result.returncode}",
        )
```

> `import shutil`、`import subprocess`、`from pathlib import Path` 已在文件顶部。

- [ ] **Step 4: 运行确认通过 + 真实编译验证**

Run: `pytest tests/test_latex.py -v`
Expected: PASS。

手动验证 tectonic 真编译（本机已装 tectonic 0.16.9）：

```bash
python - <<'PY'
import tempfile, pathlib
from mcm_agent.providers.latex import LatexProvider
d = pathlib.Path(tempfile.mkdtemp()) / "paper"; d.mkdir()
(d/"main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
r = LatexProvider().compile(d)
print("success=", r.success, "pdf=", r.pdf_path, "reason=", r.reason)
PY
```
Expected: `success= True`，生成 PDF。

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/providers/latex.py tests/test_latex.py
git commit -m "feat: LatexProvider auto-detects tectonic/latexmk/xelatex"
```

---

## Task 5: 论文导言区按 CJK 切换（中文不丢字）

**问题：** `writer.py::_write_main_files` 写死 `\documentclass[12pt]{article}` + 仅 graphicx/amsmath/booktabs，无 CJK 支持；中文内容在 tectonic(XeTeX) 下被丢弃。`ctex` 包在 tectonic 下用 Fandol 字体可自动获取。

**Files:**
- Modify: `src/mcm_agent/agents/writer.py`
- Test: `tests/test_paper_cjk_preamble.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_paper_cjk_preamble.py`：

```python
from pathlib import Path

from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.workspace import create_workspace


def _has_sections(root: Path, text: str) -> None:
    sd = root / "paper" / "sections"
    sd.mkdir(parents=True, exist_ok=True)
    for name in ["abstract", "introduction", "assumptions", "model", "results", "sensitivity", "conclusion"]:
        (sd / f"{name}.tex").write_text(f"\\section{{{name}}}\n{text}\n", encoding="utf-8")


def test_main_tex_uses_ctex_when_cjk_present(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    _has_sections(root, "本文估计粉丝投票。")
    PaperWriterAgent()._write_main_files(root / "paper")
    main = (root / "paper" / "main.tex").read_text(encoding="utf-8")
    assert "ctex" in main


def test_main_tex_plain_when_english_only(tmp_path):
    root = create_workspace(tmp_path / "ws").root
    _has_sections(root, "This paper estimates fan votes.")
    PaperWriterAgent()._write_main_files(root / "paper")
    main = (root / "paper" / "main.tex").read_text(encoding="utf-8")
    assert "ctex" not in main
    assert "\\documentclass[12pt]{article}" in main
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_paper_cjk_preamble.py -v`
Expected: FAIL（无 CJK 检测；且当前 `_write_main_files(self, paper_dir)` 不读 sections）。

- [ ] **Step 3: 实现**

修改 `writer.py::_write_main_files`，改为按 sections 内容检测 CJK 生成导言区：

```python
    def _write_main_files(self, paper_dir: Path) -> None:
        (paper_dir / "references.bib").write_text(
            "@misc{registered_sources,\n  title={Registered data sources},\n  year={2026}\n}\n",
            encoding="utf-8",
        )
        section_dir = paper_dir / "sections"
        section_text = ""
        if section_dir.exists():
            for tex in section_dir.glob("*.tex"):
                section_text += tex.read_text(encoding="utf-8")
        has_cjk = any("一" <= ch <= "鿿" for ch in section_text)
        if has_cjk:
            preamble = [
                "\\documentclass[12pt]{ctexart}",
                "\\usepackage{graphicx}",
                "\\usepackage{amsmath}",
                "\\usepackage{booktabs}",
            ]
        else:
            preamble = [
                "\\documentclass[12pt]{article}",
                "\\usepackage{graphicx}",
                "\\usepackage{amsmath}",
                "\\usepackage{booktabs}",
            ]
        body = [
            "\\begin{document}",
            "\\input{sections/abstract}",
            "\\input{sections/introduction}",
            "\\input{sections/assumptions}",
            "\\input{sections/model}",
            "\\input{sections/results}",
            "\\input{sections/sensitivity}",
            "\\input{sections/conclusion}",
            "\\bibliographystyle{plain}",
            "\\bibliography{references}",
            "\\end{document}",
            "",
        ]
        (paper_dir / "main.tex").write_text("\n".join(preamble + body), encoding="utf-8")
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `pytest tests/test_paper_cjk_preamble.py tests/test_latex.py -v`
Expected: PASS。

手动验证中文真编译（tectonic + ctexart + Fandol 自动获取，首次可能下载字体）：

```bash
python - <<'PY'
import tempfile, pathlib
from mcm_agent.agents.writer import PaperWriterAgent
from mcm_agent.core.workspace import create_workspace
from mcm_agent.providers.latex import LatexProvider
root = create_workspace(pathlib.Path(tempfile.mkdtemp())/"ws").root
sd = root/"paper"/"sections"; sd.mkdir(parents=True, exist_ok=True)
for n in ["abstract","introduction","assumptions","model","results","sensitivity","conclusion"]:
    (sd/f"{n}.tex").write_text(f"\\section{{{n}}}\n本文估计粉丝投票 fan votes。\n", encoding="utf-8")
PaperWriterAgent()._write_main_files(root/"paper")
print(LatexProvider().compile(root/"paper"))
PY
```
Expected: `success=True`，PDF 含中文（不丢字）。若 ctexart 在 tectonic 下取字体失败，回退方案：导言区改用 `\usepackage{fontspec}\usepackage{xeCJK}` 并 `\setCJKmainfont{FandolSong-Regular.otf}`，再次验证。

- [ ] **Step 5: 提交**

```bash
git add src/mcm_agent/agents/writer.py tests/test_paper_cjk_preamble.py
git commit -m "feat: language-aware latex preamble (ctex for CJK papers)"
```

---

## Task 6: 开发期真 provider smoke 脚本

**目的：** 一条命令用真实 key 跑精简流程，供阶段回归；默认不进 CI（避免费用与脆弱）。

**Files:**
- Create: `scripts/real_smoke.py`

- [ ] **Step 1: 实现脚本**

新建 `scripts/real_smoke.py`：

```python
from __future__ import annotations

import argparse
import shutil
import traceback
from pathlib import Path

from mcm_agent.config import load_settings
from mcm_agent.core.models import TaskInput
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.workflows.mvp import run_mvp_workflow

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-provider smoke (uses local API keys; costs money).")
    parser.add_argument("--problem", type=Path, required=True, help="problem .md/.pdf")
    parser.add_argument("--data", type=Path, action="append", default=[], help="data file(s)")
    parser.add_argument("--workspace", type=Path, default=Path("/tmp/mag_real_smoke"))
    parser.add_argument("--config", type=Path, default=REPO / "mcm_agent_config.local.json")
    parser.add_argument("--fast", action="store_true", help="force mineru fake to skip PDF upload")
    args = parser.parse_args()

    ws = args.workspace.resolve()
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)

    settings = load_settings(config_file=str(args.config))
    if args.fast:
        settings = settings.model_copy(update={"mineru_mode": "fake"})
    print("LLM:", settings.openai_base_url, settings.openai_model, "key_set=", bool(settings.openai_api_key))
    bundle = build_provider_bundle(settings, workspace_root=ws)
    print("llm:", type(bundle.llm).__name__, "| search:", type(bundle.search).__name__, "| latex:", bundle.latex.__class__.__name__)

    task = TaskInput(problem_file=args.problem, attachments=list(args.data), template_dir=None)
    try:
        run_mvp_workflow(ws, task, providers=bundle, settings=settings, auto_approve=True)
        print("WORKFLOW COMPLETED")
    except Exception:
        print("WORKFLOW RAISED:")
        traceback.print_exc()

    pdf = ws / "paper" / "main.pdf"
    print("PDF:", pdf, pdf.stat().st_size if pdf.exists() else "MISSING")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 静态检查**

Run: `python -c "import ast; ast.parse(open('scripts/real_smoke.py').read())"` 与 `ruff check scripts/real_smoke.py`
Expected: 无错误。

- [ ] **Step 3: 提交**

```bash
git add scripts/real_smoke.py
git commit -m "test: add real-provider smoke script (gated, manual)"
```

---

## Task 7: 阶段 1 真题回归（MCM C）

**目的：** 用真实 provider 跑 2026 MCM C，确认不崩、产出可编译 PDF。题面/数据在未跟踪的 `assets/diagnostic_2026_mcm_c/`（不提交进库）。

**Files:** 无代码改动，仅验证与记录。

- [ ] **Step 1: 全量回归**

Run: `pytest -q && ruff check src tests`
Expected: 全绿（应为 ~406+ passed）。

- [ ] **Step 2: 真题真跑（fast 模式跳过 mineru 上传）**

Run:
```bash
python scripts/real_smoke.py \
  --problem assets/diagnostic_2026_mcm_c/problem.md \
  --data assets/diagnostic_2026_mcm_c/2026_MCM_Problem_C_Data.csv \
  --fast
```
Expected: 打印 `WORKFLOW COMPLETED`（不再因 humanizer 400 崩溃）；`PDF: ... <非0字节>`。

- [ ] **Step 3: 人工确认 PDF**

打开 `/tmp/mag_real_smoke/paper/main.pdf`，确认：能打开、无中文丢字（若论文为中文）。记录此次产出仍存在的内容质量问题（摘要/Results/引用）——这些是 Phase 2 的输入，不在本阶段修复。

- [ ] **Step 4: 提交阶段收尾（如有文档更新）**

```bash
git add -A
git commit -m "docs: phase 1 real-provider pipeline verified on MCM C" || echo "nothing to commit"
```

---

## Self-Review 检查

- **Spec 覆盖**：A（Task 2 + Task 1 配置）、E（Task 3）、F（Task 4 + Task 5）、真题验收（Task 7）。D（摘要/Results/引用内容）按设计推迟至 Phase 2，已在 Task 7 Step 3 标注。
- **类型一致**：`build_providers() -> (Settings, ProviderBundle)`；`LatexProvider(command: str | None=None)`、`_resolve_command`、`_invocation` 命名一致；`_write_main_files(self, paper_dir)` 签名不变。
- **无占位符**：每个代码步骤含完整可粘贴代码与确切命令/预期。
- **回退预案**：Task 5 标注 ctexart 取字体失败时改 xeCJK+FandolSong。
