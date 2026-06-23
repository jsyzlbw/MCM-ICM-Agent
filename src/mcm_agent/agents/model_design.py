from __future__ import annotations

import json
import re
from pathlib import Path

from mcm_agent.core.model_spec import (
    ModelSpec,
    ModelVariable,
    SubproblemModel,
    read_model_spec,
    write_model_spec,
)
from mcm_agent.core.problem_type import resolve_problem_type
from mcm_agent.providers.base import TextGenerationProvider


def _safe_id(s: str, fallback: str = "q1") -> str:
    """Return a filesystem-safe subproblem_id.

    Keeps [A-Za-z0-9_-]; replaces all other characters with '_'; collapses
    consecutive underscores; strips leading/trailing underscores.  Falls back
    to *fallback* when the result would be empty.
    """
    result = re.sub(r"[^A-Za-z0-9_\-]", "_", s)
    result = re.sub(r"_+", "_", result).strip("_")
    return result if result else fallback


def _strlist(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _norm_vars(value: object) -> list[ModelVariable]:
    out: list[ModelVariable] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                symbol = str(item.get("symbol") or item.get("name") or "").strip()
                meaning = str(item.get("meaning") or item.get("description") or "").strip()
                if symbol:
                    out.append(ModelVariable(symbol=symbol, meaning=meaning))
            elif str(item).strip():
                out.append(ModelVariable(symbol=str(item).strip(), meaning=""))
    elif isinstance(value, dict):
        for symbol, meaning in value.items():
            out.append(ModelVariable(symbol=str(symbol), meaning=str(meaning)))
    return out


def _normalize_spec(data: dict) -> ModelSpec | None:
    """Coerce the many JSON shapes LLMs emit into a ModelSpec.

    Accepts {"subproblems": [...]}, {"subproblem_1": {...}, ...}, or a single model
    dict; maps alt field names (model_name/method->approach, description, steps...).
    """
    if not isinstance(data, dict):
        return None
    raw_subs: list[dict] = []
    if isinstance(data.get("subproblems"), list):
        raw_subs = [s for s in data["subproblems"] if isinstance(s, dict)]
    else:
        for key, value in data.items():
            if key == "problem_restatement":
                continue
            if isinstance(value, dict):
                raw_subs.append({**value, "_key": key})
        if not raw_subs and any(k in data for k in ("model_name", "approach", "algorithm", "title")):
            raw_subs = [data]
    subs: list[SubproblemModel] = []
    for index, raw in enumerate(raw_subs):
        approach = str(raw.get("approach") or raw.get("method") or raw.get("model_name") or "").strip()
        title = str(raw.get("title") or raw.get("model_name") or raw.get("name") or f"Subproblem {index + 1}").strip()
        assumptions = _strlist(raw.get("assumptions"))
        description = str(raw.get("description") or "").strip()
        if description and description not in assumptions:
            assumptions = [description, *assumptions]
        raw_id = str(raw.get("subproblem_id") or raw.get("_key") or f"q{index + 1}")
        subs.append(
            SubproblemModel(
                subproblem_id=_safe_id(raw_id, fallback=f"q{index + 1}"),
                title=title,
                approach=approach or title,
                variables=_norm_vars(raw.get("variables")),
                assumptions=assumptions,
                equations=_strlist(raw.get("equations") or raw.get("formulas")),
                algorithm_steps=_strlist(
                    raw.get("algorithm_steps") or raw.get("algorithm") or raw.get("steps")
                ),
                metrics=_strlist(raw.get("metrics")),
                data_inputs=_strlist(raw.get("data_inputs") or raw.get("inputs")),
            )
        )
    if not subs:
        return None
    return ModelSpec(problem_restatement=str(data.get("problem_restatement", "")), subproblems=subs)


class ModelDesignAgent:
    """Designs a problem-specific ModelSpec (the single source of truth that the
    solver implements and the writer narrates). LLM-driven, deterministic fallback."""

    def __init__(
        self,
        llm_provider: TextGenerationProvider | None = None,
        language: str = "en",
        kb_dir: Path | None = None,
    ) -> None:
        self.llm = llm_provider
        self.language = language
        self.kb_dir = kb_dir
        self.last_reason = ""

    def run(self, workspace_root: Path) -> ModelSpec:
        understanding = self._read(workspace_root / "reports" / "problem_understanding.md", 4000)
        direction = self._read(workspace_root / "discussion" / "confirmed_direction.md", 1200)
        schema = self._read(workspace_root / "results" / "schema_profile.json", 1500)
        designed = self._design(understanding, direction, schema, workspace_root=workspace_root)
        source = "llm" if designed else "fallback"
        spec = designed or self._fallback(understanding)
        write_model_spec(workspace_root, spec)
        self._write_md(workspace_root, spec, source=source)
        return spec

    def refine_from_code(self, workspace_root: Path) -> ModelSpec | None:
        """After solving, derive the ModelSpec from the code that ACTUALLY ran, so the
        paper's model section is both rich and guaranteed coherent with the computation.
        No-op (keeps the existing spec) when there is no code or no LLM.

        Per-sub mode (SC2 layout):
          code/experiments/<sub_id>.py exists for each subproblem (problem1.py is
          the alias for the first sub and is excluded from enumeration).  Each file
          is refined independently and the results are assembled into one multi-sub
          ModelSpec.

        Fallback (single-file / one-shot codegen):
          Only problem1.py is present → original single-file behaviour (1 subproblem).
        """
        if self.llm is None:
            return None

        exp_dir = workspace_root / "code" / "experiments"

        # Collect per-sub files: *.py excluding problem1.py alias
        per_sub_files: list[Path] = sorted(
            p for p in exp_dir.glob("*.py") if p.name != "problem1.py"
        ) if exp_dir.exists() else []

        # Fallback: no per-sub files → use problem1.py if it exists
        if not per_sub_files:
            fallback_path = exp_dir / "problem1.py"
            if not fallback_path.exists():
                return None
            return self._refine_single_file(workspace_root, fallback_path, sub_id=None)

        # Per-sub mode: refine each file independently
        lang = "Chinese" if self.language == "zh" else "English"
        understanding = self._read(workspace_root / "reports" / "problem_understanding.md", 1500)

        # Load nested metrics once; per-sub metrics may be a sub-dict
        metrics_raw = self._read(workspace_root / "results" / "model_metrics.json", 3000)
        try:
            metrics_all: dict = json.loads(metrics_raw) if metrics_raw else {}
        except (json.JSONDecodeError, ValueError):
            metrics_all = {}

        assembled_subs: list[SubproblemModel] = []
        for code_path in per_sub_files:
            sub_id = _safe_id(code_path.stem, fallback=f"q{len(assembled_subs) + 1}")
            code = code_path.read_text(encoding="utf-8")[:8000]
            # Per-sub metrics: nested dict or entire flat metrics as fallback
            sub_metrics = metrics_all.get(sub_id, metrics_all) if metrics_all else {}
            metrics_str = json.dumps(sub_metrics, ensure_ascii=False)[:500] if sub_metrics else ""
            system = (
                "You are a mathematical-modeling writer. Describe the model THIS code actually "
                "implements (variables, assumptions, equations in LaTeX, algorithm steps, metrics) "
                "as JSON: {\"subproblems\": [{\"subproblem_id\": str, \"title\": str, \"approach\": str, "
                "\"variables\":[{\"symbol\": str, \"meaning\": str}], \"assumptions\":[str], "
                "\"equations\":[str], \"algorithm_steps\":[str], \"metrics\":[str]}]}. "
                f"Write prose fields in {lang}; keep symbols/equations in LaTeX. Be faithful to the code."
            )
            prompt = (
                f"FILE: {sub_id}\n"
                f"PROBLEM (context):\n{understanding}\n\n"
                f"CODE THAT RAN:\n{code}\n\n"
                f"METRICS PRODUCED:\n{metrics_str}"
            )
            try:
                data = self._parse(self.llm.generate(system, prompt).content)
            except Exception as exc:
                self.last_reason = f"refine call for {sub_id} failed: {type(exc).__name__}: {exc}"
                continue  # skip this sub, keep going
            sub_spec = _normalize_spec(data)
            if sub_spec and sub_spec.subproblems:
                # Override the sub_id to match the file stem (LLM may guess wrong)
                sub = sub_spec.subproblems[0]
                sub.subproblem_id = sub_id
                assembled_subs.append(sub)

        if not assembled_subs:
            self.last_reason = "all per-sub refine calls failed or yielded no subproblems"
            return None

        # Preserve problem_restatement from existing on-disk spec
        existing = read_model_spec(workspace_root)
        restatement = (existing.problem_restatement if existing else "") or ""

        spec = ModelSpec(problem_restatement=restatement, subproblems=assembled_subs)
        write_model_spec(workspace_root, spec)
        self._write_md(workspace_root, spec, source="llm")
        return spec

    def _refine_single_file(
        self, workspace_root: Path, code_path: Path, sub_id: str | None
    ) -> ModelSpec | None:
        """Original single-file refine behaviour (fallback / one-shot codegen path)."""
        code = code_path.read_text(encoding="utf-8")[:8000]
        metrics = self._read(workspace_root / "results" / "model_metrics.json", 1500)
        understanding = self._read(workspace_root / "reports" / "problem_understanding.md", 1500)
        lang = "Chinese" if self.language == "zh" else "English"
        system = (
            "You are a mathematical-modeling writer. Describe the model THIS code actually "
            "implements (variables, assumptions, equations in LaTeX, algorithm steps, metrics) "
            "as JSON: {\"subproblems\": [{\"subproblem_id\": str, \"title\": str, \"approach\": str, "
            "\"variables\":[{\"symbol\": str, \"meaning\": str}], \"assumptions\":[str], "
            "\"equations\":[str], \"algorithm_steps\":[str], \"metrics\":[str]}]}. "
            f"Write prose fields in {lang}; keep symbols/equations in LaTeX. Be faithful to the code."
        )
        if sub_id:
            prompt = (
                f"FILE: {sub_id}\n"
                f"PROBLEM (context):\n{understanding}\n\n"
                f"CODE THAT RAN:\n{code}\n\n"
                f"METRICS PRODUCED:\n{metrics}"
            )
        else:
            prompt = f"PROBLEM (context):\n{understanding}\n\nCODE THAT RAN:\n{code}\n\nMETRICS PRODUCED:\n{metrics}"
        try:
            data = self._parse(self.llm.generate(system, prompt).content)
        except Exception as exc:
            self.last_reason = f"refine call failed: {type(exc).__name__}: {exc}"
            return None
        spec = _normalize_spec(data)
        if not spec or not spec.subproblems:
            self.last_reason = "refine output had no usable subproblems"
            return None
        if not spec.problem_restatement:
            existing = read_model_spec(workspace_root)
            if existing is not None:
                spec.problem_restatement = existing.problem_restatement
        write_model_spec(workspace_root, spec)
        self._write_md(workspace_root, spec, source="llm")
        return spec

    def _enumerate_tasks(self, understanding: str) -> list[str]:
        """Call the LLM with a focused prompt that ONLY enumerates the problem's tasks.

        Returns a list of short task title strings (3–5 typical for MCM/ICM).
        Returns [] on failure or when no LLM is available.
        """
        if self.llm is None:
            return []
        system = (
            "List EVERY distinct task / sub-question the problem asks the team to do, "
            "as a JSON array of short title strings. Contest problems usually have 3–5 distinct tasks. "
            "Do NOT merge multiple asks into one and do NOT omit any. "
            "Output ONLY a JSON array of strings."
        )
        prompt = f"PROBLEM UNDERSTANDING:\n{understanding}"
        try:
            raw = self.llm.generate(system, prompt).content
        except Exception as exc:
            self.last_reason = f"enumerate_tasks call failed: {type(exc).__name__}: {exc}"
            return []
        # _parse expects a dict, so handle bare array or {"tasks": [...]} shapes
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text.rstrip())
        # Try bare array first
        array_match = re.search(r"\[.*\]", text, re.DOTALL)
        if array_match:
            try:
                parsed = json.loads(array_match.group(0))
                if isinstance(parsed, list):
                    return [str(t).strip() for t in parsed if str(t).strip()]
            except json.JSONDecodeError:
                pass
        # Try dict with "tasks" key
        data = self._parse(raw)
        if isinstance(data.get("tasks"), list):
            return [str(t).strip() for t in data["tasks"] if str(t).strip()]
        return []

    def _build_design_prompt(
        self,
        understanding: str,
        direction: str,
        schema: str,
        lang: str,
        tasks: list[str] | None = None,
        retry: bool = False,
        got: int = 0,
        pattern_card: str = "",
    ) -> tuple[str, str]:
        """Build (system, prompt) strings for the design LLM call.

        Separated so tests can assert on the exact text without needing to call
        the LLM.

        When *tasks* is non-empty the prompt explicitly lists every task title
        so the LLM knows which sub-questions must each get their own subproblem.
        When *retry* is True a stronger instruction is prepended noting the
        previous under-count.
        When *pattern_card* is non-empty it is appended to the prompt to ground
        the model choice in real award-winning practice (KB1).
        """
        system = (
            "You are a mathematical-modeling architect. Design a problem-specific model "
            "(not a generic template) for each sub-problem.\n\n"
            "STEP 1 — Extract tasks: Before writing any subproblem, enumerate every explicit "
            "task or sub-question the problem asks. Look for: numbered questions (Task 1, Q1, 1., etc.), "
            "imperative verbs ('estimate', 'compare', 'determine', 'propose', 'evaluate', 'predict', "
            "'design', 'analyze'), and distinct asks in separate sentences or paragraphs. "
            "List every task you find.\n\n"
            "STEP 2 — One subproblem per task: Create EXACTLY ONE subproblem for each task you "
            "extracted in Step 1. Do NOT merge multiple tasks into one subproblem, and do NOT omit "
            "any task. Contest problems typically have 3–5 distinct tasks; if you find only 1, "
            "re-read carefully for additional asks before finalizing.\n\n"
            "Respond ONLY with JSON matching: "
            '{"problem_restatement": str, "subproblems": [{"subproblem_id": str, "title": str, '
            '"approach": str, "variables": [{"symbol": str, "meaning": str}], "assumptions": [str], '
            '"equations": [str (LaTeX, no $)], "algorithm_steps": [str], "metrics": [str], '
            '"data_inputs": [str]}]}. '
            f"Write meaning/title/assumptions in {lang}; keep symbols and equations in LaTeX."
        )
        prompt_parts = [
            "PROBLEM UNDERSTANDING:",
            understanding,
            "\nCONFIRMED DIRECTION:",
            direction,
            "\nDATA SCHEMA:",
            schema,
        ]
        if tasks:
            numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
            task_block = (
                f"\nPRE-ENUMERATED TASKS (you MUST design EXACTLY ONE subproblem for EACH):\n"
                f"{numbered}\n"
                f"Total tasks: {len(tasks)}. Keep their order. Do not merge or omit any."
            )
            if retry:
                task_block = (
                    f"\nWARNING — RETRY: your previous response returned {got} subproblem(s) "
                    f"but there are {len(tasks)} tasks. You must return EXACTLY one subproblem "
                    f"for each of the {len(tasks)} tasks listed below — no merging, no omitting.\n"
                    f"{numbered}\n"
                    f"Total required subproblems: {len(tasks)}."
                )
            prompt_parts.append(task_block)
        else:
            prompt_parts.append(
                "\nStep 1: List all tasks/sub-questions the problem asks (one line each)."
                "\nStep 2: Design one subproblem per task — do not merge, do not omit any task."
                "\nContest problems typically have 3–5 separate tasks; cover all of them."
            )
        if pattern_card:
            prompt_parts.append(pattern_card)
        return system, "\n".join(prompt_parts)

    def _pattern_card_block(self, workspace_root: Path) -> str:
        """Return a prompt block summarising outstanding-paper patterns for this problem type.

        Returns "" (empty string) on any failure or when kb_dir is None — callers can
        safely append this to any prompt without checking.
        """
        if self.kb_dir is None:
            return ""
        try:
            ptype = resolve_problem_type(workspace_root, self.llm)
            if not ptype:
                return ""
            pattern_file = self.kb_dir / "patterns" / f"{ptype}.json"
            if not pattern_file.exists():
                return ""
            data = json.loads(pattern_file.read_text(encoding="utf-8"))
            # Build summary sections
            lines: list[str] = [
                "",
                "OUTSTANDING-PAPER PATTERNS (problem type: " + ptype + "):",
                (
                    "Below are modeling patterns distilled from past Outstanding papers of THIS "
                    "problem type — use them to inform model CHOICE and to AVOID known pitfalls; "
                    "do NOT copy any specific paper's content; your model must be original to this problem."
                ),
            ]
            models = data.get("common_models") or []
            if models:
                names = ", ".join(m["name"] for m in models if isinstance(m, dict) and m.get("name"))
                if names:
                    lines.append(f"Common models in past winners: {names}.")
            techniques = data.get("common_techniques") or []
            if techniques:
                lines.append("Common techniques: " + "; ".join(str(t) for t in techniques) + ".")
            pitfalls = data.get("recurring_pitfalls") or []
            if pitfalls:
                lines.append("Recurring pitfalls to avoid: " + "; ".join(str(p) for p in pitfalls) + ".")
            patterns = data.get("reusable_patterns") or []
            if patterns:
                lines.append("Reusable patterns: " + "; ".join(str(p) for p in patterns) + ".")
            return "\n".join(lines)
        except Exception:
            return ""

    def _design(self, understanding: str, direction: str, schema: str, workspace_root: Path | None = None) -> ModelSpec | None:
        if self.llm is None:
            self.last_reason = "no LLM provider"
            return None
        lang = "Chinese" if self.language == "zh" else "English"

        # COV1: enumerate tasks first with a focused call
        tasks = self._enumerate_tasks(understanding)

        # KB1: build pattern card block for this problem type (empty string when disabled)
        pattern_card = self._pattern_card_block(workspace_root) if workspace_root is not None else ""

        system, prompt = self._build_design_prompt(
            understanding, direction, schema, lang, tasks=tasks, pattern_card=pattern_card
        )
        try:
            data = self._parse(self.llm.generate(system, prompt).content)
        except Exception as exc:
            self.last_reason = f"design call failed: {type(exc).__name__}: {exc}"
            return None
        spec = _normalize_spec(data)

        # COV1: if tasks were enumerated and we got too few subproblems, retry once
        if tasks and (spec is None or len(spec.subproblems) < len(tasks)):
            got = len(spec.subproblems) if spec else 0
            retry_system, retry_prompt = self._build_design_prompt(
                understanding, direction, schema, lang, tasks=tasks, retry=True, got=got,
                pattern_card=pattern_card,
            )
            try:
                retry_data = self._parse(self.llm.generate(retry_system, retry_prompt).content)
                retry_spec = _normalize_spec(retry_data)
                if retry_spec and (spec is None or len(retry_spec.subproblems) > len(spec.subproblems)):
                    spec = retry_spec
            except Exception:
                pass  # keep whatever spec we have from the first call

        # COV1: backfill — if still short, append placeholder subproblems for missing tasks
        if tasks and (spec is None or len(spec.subproblems) < len(tasks)):
            existing_titles = {s.title.lower() for s in (spec.subproblems if spec else [])}
            placeholders: list[SubproblemModel] = []
            # Append one placeholder per task that has no matching subproblem by index
            existing_subs = list(spec.subproblems) if spec else []
            for i, task_title in enumerate(tasks):
                if i < len(existing_subs):
                    continue  # already covered by index
                # Check if this task title is represented by title match
                if task_title.lower() in existing_titles:
                    continue
                placeholders.append(
                    SubproblemModel(
                        subproblem_id=_safe_id(task_title, fallback=f"q{i+1}"),
                        title=task_title,
                        approach=f"Problem-specific approach for: {task_title}",
                        variables=[],
                        assumptions=[],
                        equations=[],
                        algorithm_steps=[],
                        metrics=[],
                        data_inputs=[],
                    )
                )
            if placeholders:
                restatement = spec.problem_restatement if spec else ""
                all_subs = existing_subs + placeholders
                spec = ModelSpec(problem_restatement=restatement, subproblems=all_subs)

        if spec and spec.subproblems:
            return spec
        self.last_reason = "design output had no usable subproblems after normalization"
        return None

    def _fallback(self, understanding: str) -> ModelSpec:
        restate = " ".join(understanding.split())[:300] if understanding else "Contest problem."
        return ModelSpec(
            problem_restatement=restate,
            subproblems=[
                SubproblemModel(
                    subproblem_id="q1",
                    title="Primary model" if self.language != "zh" else "主模型",
                    approach="problem-specific model",
                    variables=[ModelVariable(symbol="x", meaning="input data")],
                    assumptions=["Inputs are representative of the problem conditions."],
                    algorithm_steps=["Load data", "Fit/compute the model", "Report metrics"],
                    metrics=["primary_metric"],
                )
            ],
        )

    def _write_md(self, workspace_root: Path, spec: ModelSpec, *, source: str = "llm") -> None:
        status = "LLM-designed" if source == "llm" else f"fallback ({self.last_reason or 'unknown'})"
        lines = ["# Model Spec", "", f"<!-- spec source: {status} -->", "", spec.problem_restatement, ""]
        for sub in spec.subproblems:
            lines.append(f"## {sub.subproblem_id}: {sub.title}")
            lines.append(f"Approach: {sub.approach}")
            if sub.variables:
                lines.append("Variables: " + ", ".join(f"{v.symbol} ({v.meaning})" for v in sub.variables))
            if sub.assumptions:
                lines.extend(["Assumptions:", *(f"- {a}" for a in sub.assumptions)])
            if sub.equations:
                lines.extend(["Equations:", *(f"- {e}" for e in sub.equations)])
            if sub.algorithm_steps:
                lines.extend(["Algorithm:", *(f"{i+1}. {s}" for i, s in enumerate(sub.algorithm_steps))])
            if sub.metrics:
                lines.append("Metrics: " + ", ".join(sub.metrics))
            lines.append("")
        (workspace_root / "reports" / "model_spec.md").write_text("\n".join(lines), encoding="utf-8")

    def _read(self, path: Path, limit: int) -> str:
        return path.read_text(encoding="utf-8")[:limit] if path.exists() else ""

    def _parse(self, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text.rstrip())
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
