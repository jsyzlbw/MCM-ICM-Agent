from __future__ import annotations

from pathlib import Path

_GUIDANCE = (
    "我已记录你的想法。要正式分析题目、与我深入讨论研究方向，请运行 /start；"
    "需要配置 LLM 请运行 /api。"
)


def _is_unconfigured(llm_provider: object | None) -> bool:
    """A None or Fake provider means the LLM is not really configured."""
    return llm_provider is None or type(llm_provider).__name__ == "FakeLLMProvider"


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
    attachments: list[tuple[str, str]] | None = None,
) -> str:
    """Conversational reply for the interactive CLI.

    Uses the real LLM with problem + recent-discussion context. Distinguishes the
    three failure modes so the user never gets a misleading message:
      - LLM not configured (None/Fake)  -> guidance to run /api
      - LLM call fails (network/API)    -> honest error WITH the reason
      - model returns nothing           -> retry hint
    """
    if _is_unconfigured(llm_provider):
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
            "\n\n".join(f"ATTACHED FILE {name}:\n{content}" for name, content in (attachments or [])),
            f"USER:\n{message}",
        ]
        if part
    )
    try:
        reply = llm_provider.generate(system, prompt).content.strip()
    except Exception as exc:  # noqa: BLE001 - surface the real reason, don't hide it
        reason = str(exc).strip() or type(exc).__name__
        return (
            f"⚠️ LLM 调用失败：{reason}\n"
            "（这通常是网络或接口问题，不是没配置。）请检查网络后重试，"
            "或运行 /api 选 [4] 测连通 定位。"
        )
    return reply or "（模型未返回内容，请重试，或换一种问法。）"
