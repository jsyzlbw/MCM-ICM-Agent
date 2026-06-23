"""KB0 — resolve the current problem's type for KB-scoped retrieval.

``resolve_problem_type`` maps the workspace's problem to one of the taxonomy
labels used in the corpus KB.  Resolution order:

1. Cache: ``reports/problem_type.json`` already has a valid label → return it.
2. Taxonomy lookup: ``reports/problem_meta.json`` has ``year`` + ``letter``
   (integers / strings) → ``corpus.taxonomy.problem_type``.  Skips on "unknown".
3. LLM fallback: ``llm`` provided **and** ``reports/problem_understanding.md``
   exists → ask the LLM to pick one label; validate; write cache; return it.
4. None — no information available or every path errored.

The function **never raises**.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mcm_agent.corpus.taxonomy import problem_type as _taxonomy_lookup
from mcm_agent.utils.json_io import read_json, write_json

_ALLOWED_LABELS: frozenset[str] = frozenset(
    [
        "continuous",
        "discrete",
        "data",
        "operations_research",
        "sustainability",
        "policy",
        "interdisciplinary",
    ]
)

_CACHE_FILENAME = "problem_type.json"
_META_FILENAME = "problem_meta.json"
_UNDERSTANDING_FILENAME = "problem_understanding.md"

_LLM_SYSTEM = (
    "Classify this MCM/ICM problem into exactly one of: "
    "continuous, discrete, data, operations_research, sustainability, "
    "policy, interdisciplinary. Output only the single label."
)


def resolve_problem_type(
    workspace_root: Path, llm: object | None = None
) -> str | None:
    """Return the problem-type label for this workspace, or None if unknown.

    Parameters
    ----------
    workspace_root:
        Root of the mag workspace (the directory that contains ``reports/``).
    llm:
        Optional LLM provider with a ``generate(system, prompt) -> ProviderResult``
        method.  Used only when the taxonomy lookup cannot determine the type.
    """
    reports = workspace_root / "reports"

    # ------------------------------------------------------------------
    # 1. Cache hit
    # ------------------------------------------------------------------
    try:
        cache_path = reports / _CACHE_FILENAME
        if cache_path.exists():
            data: Any = read_json(cache_path, {})
            label = str(data.get("problem_type", "")).strip().lower()
            if label in _ALLOWED_LABELS:
                return label
    except Exception:
        pass

    # ------------------------------------------------------------------
    # 2. Taxonomy lookup via problem_meta.json
    # ------------------------------------------------------------------
    try:
        meta_path = reports / _META_FILENAME
        if meta_path.exists():
            meta: Any = read_json(meta_path, {})
            year = meta.get("year")
            letter = meta.get("letter")
            if isinstance(year, int) and isinstance(letter, str):
                result = _taxonomy_lookup(year, letter)
                if result != "unknown":
                    return result
    except Exception:
        pass

    # ------------------------------------------------------------------
    # 3. LLM fallback
    # ------------------------------------------------------------------
    if llm is not None:
        try:
            understanding_path = reports / _UNDERSTANDING_FILENAME
            if understanding_path.exists():
                problem_text = understanding_path.read_text(encoding="utf-8")
                provider_result = llm.generate(_LLM_SYSTEM, problem_text)
                label = provider_result.content.strip().lower()
                if label in _ALLOWED_LABELS:
                    write_json(
                        reports / _CACHE_FILENAME,
                        {"problem_type": label, "source": "llm"},
                    )
                    return label
        except Exception:
            pass

    return None
