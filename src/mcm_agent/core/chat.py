from __future__ import annotations

from pathlib import Path

_GUIDANCE = (
    "我已记录你的想法。要正式分析题目、与我深入讨论研究方向，请运行 /start；"
    "需要配置 LLM 请运行 /api。"
)


def _problem_excerpt(workspace_root: Path, limit: int = 1500) -> str:
    problem_dir = workspace_root / "input" / "problem"
    if not problem_dir.exists():
        return ""
    files = sorted(path for path in problem_dir.iterdir() if path.is_file())
    if not files:
        return ""
    try:
        return files[0].read_text(encoding="utf-8")[:limit]
    except UnicodeDecodeError:
        return ""


def generate_chat_reply(
    workspace_root: Path,
    message: str,
    llm_provider: object | None,
    recent_messages: list[dict[str, object]] | None,
) -> str:
    """Conversational reply for the interactive CLI.

    Uses the real LLM with problem + recent-discussion context. Falls back to a
    guidance message when no LLM is configured or the model returns nothing.
    """
    if llm_provider is None:
        return _GUIDANCE
    problem = _problem_excerpt(Path(workspace_root))
    history = "\n".join(
        f"{item.get('role')}: {item.get('content')}"
        for item in (recent_messages or [])[-6:]
        if isinstance(item, dict)
    )
    system = (
        "You are Mag, a math-modeling (MCM/ICM) research assistant. Discuss the problem, "
        "clarify the research direction, and give concrete, actionable modeling advice. "
        "Reply in the user's language."
    )
    prompt = "\n\n".join(
        part
        for part in [
            f"PROBLEM:\n{problem}" if problem else "",
            f"RECENT DISCUSSION:\n{history}" if history else "",
            f"USER:\n{message}",
        ]
        if part
    )
    try:
        reply = llm_provider.generate(system, prompt).content.strip()
    except Exception:
        return _GUIDANCE
    return reply or _GUIDANCE
