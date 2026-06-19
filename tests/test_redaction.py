from pathlib import Path

from mcm_agent.core.redaction import redact_secrets
from mcm_agent.core.session_store import SessionStore
from mcm_agent.core.workspace import create_workspace


def test_redact_secrets_masks_key_option_keeps_others() -> None:
    text = "/init --llm-key sk-595bc83197ce4d06a7a322e7b31e70e8 --llm-base-url https://x/v1 --llm-model m"
    out = redact_secrets(text)
    assert "sk-595bc83197ce4d06a7a322e7b31e70e8" not in out
    assert "--llm-key ***" in out
    assert "--llm-base-url https://x/v1" in out  # non-secret preserved
    assert "--llm-model m" in out


def test_redact_secrets_masks_standalone_sk_token() -> None:
    assert "sk-ABCDEF0123456789ABCD" not in redact_secrets("my key is sk-ABCDEF0123456789ABCD ok")


def test_redact_secrets_passthrough_plain_text() -> None:
    assert redact_secrets("帮我分析这道题") == "帮我分析这道题"


def test_session_store_redacts_api_key(tmp_path: Path) -> None:
    store = SessionStore(create_workspace(tmp_path / "ws").root)
    store.append_message("user", "/init --llm-key sk-595bc83197ce4d06a7a322e7b31e70e8 --llm-model m")
    content = str(store.read_recent_messages()[-1]["content"])
    assert "sk-595bc83197ce4d06a7a322e7b31e70e8" not in content
    assert "***" in content
