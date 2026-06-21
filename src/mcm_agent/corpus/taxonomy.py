from __future__ import annotations

# Modern MCM/ICM (2016+): A/B/C are MCM, D/E/F are ICM.
_MODERN = {
    "A": "continuous",
    "B": "discrete",
    "C": "data",
    "D": "operations_research",
    "E": "sustainability",
    "F": "policy",
}
# Early years (pre-2016) used C as the single interdisciplinary (ICM) problem.
_EARLY = {"A": "continuous", "B": "discrete", "C": "interdisciplinary"}


def problem_type(year: int, letter: str) -> str:
    letter = (letter or "").strip().upper()[:1]
    table = _MODERN if year >= 2016 else _EARLY
    return table.get(letter, "unknown")
