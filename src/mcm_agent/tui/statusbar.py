from __future__ import annotations


def bottom_toolbar(state: object, settings: object) -> str:
    llm = getattr(settings, "openai_model", "") if getattr(settings, "openai_api_key", "") else "未配置"
    phase = str(getattr(state, "phase", ""))
    return f" {llm} · {phase}    ? 快捷键 · ! shell · @ 文件 "
