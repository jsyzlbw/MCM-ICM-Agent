from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from mcm_agent.core.models import SourceRecord


class WorldBankProvider:
    def __init__(self, workspace_data_dir: Path) -> None:
        self.data_dir = workspace_data_dir

    def fetch_indicator(self, country: str, indicator: str) -> SourceRecord:
        response = httpx.get(
            f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}",
            params={"format": "json"},
            timeout=60,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"World Bank fetch failed: {response.status_code}")
        raw_dir = self.data_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        local_path = raw_dir / f"worldbank_{country}_{indicator}.json"
        local_path.write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
        return SourceRecord(
            source_id=f"worldbank_{country}_{indicator}",
            title=f"World Bank {indicator} for {country}",
            url=str(response.url),
            accessed_at=datetime.now(UTC),
            license="World Bank open data",
            provider="world_bank_api",
            source_rank="official",
            used_for=f"{indicator} feature construction",
            citation="World Bank Open Data",
            local_path=str(local_path),
        )
