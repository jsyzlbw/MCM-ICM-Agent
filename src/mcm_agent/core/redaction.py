from __future__ import annotations

import re

# `--llm-key VALUE` / `--xxx-token=VALUE` etc. (the value, not the flag name).
_OPTION_RE = re.compile(r"(--[\w-]*(?:key|token|secret|password))(\s+|=)(\S+)", re.IGNORECASE)
# Standalone provider-style secrets, e.g. OpenAI/DeepSeek `sk-...` tokens.
_TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b")


def redact_secrets(text: str) -> str:
    """Mask API keys/tokens in free text before it is persisted or sent to an LLM.

    Keeps non-secret context (flag names, base URLs, model names) intact.
    """
    text = _OPTION_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}***", text)
    text = _TOKEN_RE.sub("***", text)
    return text
