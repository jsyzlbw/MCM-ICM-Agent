from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def default_config() -> dict[str, Any]:
    return {
        "llm": {
            "provider": "openai_compatible",
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4.1",
            "timeout_seconds": 60,
        },
        "search": {
            "tavily_api_key": "",
            "firecrawl_api_key": "",
            "brave_search_api_key": "",
            "exa_api_key": "",
        },
        "official_data": {
            "fred_api_key": "",
            "open_meteo_base_url": "https://archive-api.open-meteo.com/v1/archive",
            "oecd_base_url": "https://sdmx.oecd.org/public/rest/v1/data",
            "undata_base_url": "https://data.un.org/Handlers/DownloadHandler.ashx",
            "us_census_api_key": "",
            "us_census_base_url": "https://api.census.gov/data",
            "noaa_api_key": "",
            "noaa_base_url": "https://www.ncei.noaa.gov/cdo-web/api/v2",
            "nasa_power_base_url": "https://power.larc.nasa.gov/api/temporal/daily/point",
            "overpass_base_url": "https://overpass-api.de/api/interpreter",
        },
        "mineru": {
            "mode": "fake",
            "cli": "mineru",
            "api_base_url": "https://mineru.net",
            "api_key": "",
        },
        "humanizer": {
            "provider": "fake",
            "api_key": "",
            "api_base_url": "https://leahloveswriting.xyz",
        },
        "rag": {
            "knowledge_base_dir": "knowledge_base",
            "ingest_extensions": [".md", ".txt", ".pdf"],
        },
        "embedding": {
            "provider": "voyage",
            "api_key": "",
            "base_url": "https://api.voyageai.com/v1",
            "embedding_model": "voyage-3-large",
            "rerank_model": "rerank-2",
        },
        "runtime": {
            "default_language": "en",
            "max_retries": 2,
            "http_timeout_seconds": 60,
            "code_timeout_seconds": 120,
        },
    }


def read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_config()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"GUI config must be a JSON object: {path}")
    return payload


def write_config(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def mask_config(payload: dict[str, Any]) -> dict[str, Any]:
    return _mask_node(deepcopy(payload))


def merge_config(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``incoming`` into ``existing`` for safe round-trips from the masked GUI.

    - Mask pseudo-fields (``*_configured`` / ``*_preview``) are dropped.
    - Secret keys with an empty/blank incoming value are skipped so the stored
      secret is preserved (the GUI never sees the real secret to send back).
    - Everything else overwrites.
    """
    result = deepcopy(existing) if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if key.endswith("_configured") or key.endswith("_preview"):
            continue
        if isinstance(value, dict):
            base = result.get(key)
            result[key] = merge_config(base if isinstance(base, dict) else {}, value)
            continue
        if _is_secret_key(key) and (value is None or value == ""):
            continue
        result[key] = value
    return result


def _mask_node(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, child in value.items():
            if _is_secret_key(key):
                secret = str(child or "")
                masked[f"{key}_configured"] = bool(secret)
                masked[f"{key}_preview"] = secret[-4:] if secret else ""
                continue
            masked[key] = _mask_node(child)
        return masked
    if isinstance(value, list):
        return [_mask_node(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    return key == "api_key" or key.endswith("_api_key")
