from mcm_agent.server.config_store import merge_config


def test_merge_preserves_existing_secret_when_incoming_blank() -> None:
    existing = {"llm": {"api_key": "secret123", "model": "gpt-4.1"}}
    incoming = {"llm": {"api_key": "", "model": "gpt-4o"}}

    merged = merge_config(existing, incoming)

    assert merged["llm"]["api_key"] == "secret123"  # preserved
    assert merged["llm"]["model"] == "gpt-4o"  # overwritten


def test_merge_strips_mask_pseudo_fields() -> None:
    existing = {"llm": {"api_key": "secret123"}}
    incoming = {"llm": {"api_key_configured": True, "api_key_preview": "t123", "model": "x"}}

    merged = merge_config(existing, incoming)

    assert "api_key_configured" not in merged["llm"]
    assert "api_key_preview" not in merged["llm"]
    assert merged["llm"]["api_key"] == "secret123"
    assert merged["llm"]["model"] == "x"


def test_merge_overwrites_secret_when_provided() -> None:
    existing = {"llm": {"api_key": "old"}}
    incoming = {"llm": {"api_key": "new"}}

    assert merge_config(existing, incoming)["llm"]["api_key"] == "new"


def test_merge_adds_new_section() -> None:
    merged = merge_config({"llm": {"model": "x"}}, {"search": {"tavily_api_key": "k"}})

    assert merged["llm"]["model"] == "x"
    assert merged["search"]["tavily_api_key"] == "k"
