from __future__ import annotations

import json
import re
from pathlib import Path

from mcm_agent.core.model_spec import (
    ModelSpec,
    ModelVariable,
    SubproblemModel,
    write_model_spec,
)
from mcm_agent.providers.base import TextGenerationProvider


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
        subs.append(
            SubproblemModel(
                subproblem_id=str(raw.get("subproblem_id") or raw.get("_key") or f"q{index + 1}"),
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

    def __init__(self, llm_provider: TextGenerationProvider | None = None, language: str = "en") -> None:
        self.llm = llm_provider
        self.language = language

    def run(self, workspace_root: Path) -> ModelSpec:
        understanding = self._read(workspace_root / "reports" / "problem_understanding.md", 4000)
        direction = self._read(workspace_root / "discussion" / "confirmed_direction.md", 1200)
        schema = self._read(workspace_root / "results" / "schema_profile.json", 1500)
        spec = self._design(understanding, direction, schema) or self._fallback(understanding)
        write_model_spec(workspace_root, spec)
        self._write_md(workspace_root, spec)
        return spec

    def _design(self, understanding: str, direction: str, schema: str) -> ModelSpec | None:
        if self.llm is None:
            return None
        lang = "Chinese" if self.language == "zh" else "English"
        system = (
            "You are a mathematical-modeling architect. Design a problem-specific model "
            "(not a generic template) for each sub-problem. Respond ONLY with JSON matching: "
            '{"problem_restatement": str, "subproblems": [{"subproblem_id": str, "title": str, '
            '"approach": str, "variables": [{"symbol": str, "meaning": str}], "assumptions": [str], '
            '"equations": [str (LaTeX, no $)], "algorithm_steps": [str], "metrics": [str], '
            '"data_inputs": [str]}]}. '
            f"Write meaning/title/assumptions in {lang}; keep symbols and equations in LaTeX."
        )
        prompt = "\n".join(
            [
                "PROBLEM UNDERSTANDING:",
                understanding,
                "\nCONFIRMED DIRECTION:",
                direction,
                "\nDATA SCHEMA:",
                schema,
                "\nDesign the model(s). One subproblem per task in the problem.",
            ]
        )
        try:
            data = self._parse(self.llm.generate(system, prompt).content)
        except Exception:
            return None
        spec = _normalize_spec(data)
        return spec if spec and spec.subproblems else None

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

    def _write_md(self, workspace_root: Path, spec: ModelSpec) -> None:
        lines = ["# Model Spec", "", spec.problem_restatement, ""]
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
