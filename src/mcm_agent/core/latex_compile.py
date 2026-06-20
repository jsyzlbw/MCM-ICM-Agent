from __future__ import annotations

import json
import re
from pathlib import Path

from mcm_agent.core.latex_text import markdown_to_latex

_SYSTEM = (
    "You are a LaTeX build fixer. Given a tectonic/LaTeX error log and the current "
    "section files, return corrected LaTeX. Respond ONLY with a JSON object mapping "
    "section filename to its full corrected LaTeX content. Keep \\section headers and "
    "the paper's language; only fix what breaks compilation."
)


def compile_with_repair(
    paper_dir: Path,
    latex_provider: object,
    llm: object | None = None,
    *,
    language: str = "en",
    max_attempts: int = 4,
) -> object:
    """Compile LaTeX; on failure, let the LLM fix the offending sections and
    recompile, looping until it compiles or attempts run out."""
    result = latex_provider.compile(paper_dir)
    if getattr(result, "success", False) or llm is None:
        return result

    section_dir = paper_dir / "sections"
    for _ in range(max_attempts):
        log_excerpt = _read_log(result, paper_dir)
        sections = _read_sections(section_dir)
        if not sections:
            break
        prompt = _repair_prompt(log_excerpt, sections, language)
        try:
            raw = llm.generate(_SYSTEM, prompt).content
            fixes = _parse_fixes(raw)
        except Exception:
            break
        if not fixes:
            break
        for name, content in fixes.items():
            target = section_dir / Path(str(name)).name
            if target.parent != section_dir:
                continue
            target.write_text(markdown_to_latex(str(content)).rstrip() + "\n", encoding="utf-8")
        result = latex_provider.compile(paper_dir)
        if getattr(result, "success", False):
            return result
    return result


def _read_log(result: object, paper_dir: Path) -> str:
    log_path = getattr(result, "log_path", "") or ""
    path = Path(log_path) if log_path else paper_dir / "compile_log.txt"
    text = path.read_text(encoding="utf-8") if path.exists() else str(getattr(result, "reason", ""))
    return text[-2000:]


def _read_sections(section_dir: Path) -> dict[str, str]:
    if not section_dir.exists():
        return {}
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(section_dir.glob("*.tex"))
    }


def _repair_prompt(log_excerpt: str, sections: dict[str, str], language: str) -> str:
    return "\n".join(
        [
            f"Paper language: {language}",
            "LaTeX error log (tail):",
            log_excerpt,
            "",
            "Current section files (JSON):",
            json.dumps(sections, ensure_ascii=False, indent=2),
            "",
            "Return ONLY a JSON object {filename: corrected_latex} for files you changed.",
        ]
    )


def _parse_fixes(raw: str) -> dict[str, str]:
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
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if str(k).endswith(".tex")}
