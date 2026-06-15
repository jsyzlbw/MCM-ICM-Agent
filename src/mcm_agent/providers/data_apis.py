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


class OfficialDataApiRepairProvider:
    def __init__(
        self,
        *,
        fred_api_key: str = "",
        open_meteo_base_url: str = "https://archive-api.open-meteo.com/v1/archive",
        oecd_base_url: str = "https://sdmx.oecd.org/public/rest/v1/data",
        undata_base_url: str = "https://data.un.org/Handlers/DownloadHandler.ashx",
        us_census_api_key: str = "",
        us_census_base_url: str = "https://api.census.gov/data",
        noaa_api_key: str = "",
        noaa_base_url: str = "https://www.ncei.noaa.gov/cdo-web/api/v2",
        nasa_power_base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point",
        overpass_base_url: str = "https://overpass-api.de/api/interpreter",
    ) -> None:
        self.fred_api_key = fred_api_key
        self.open_meteo_base_url = open_meteo_base_url
        self.oecd_base_url = oecd_base_url
        self.undata_base_url = undata_base_url
        self.us_census_api_key = us_census_api_key
        self.us_census_base_url = us_census_base_url
        self.noaa_api_key = noaa_api_key
        self.noaa_base_url = noaa_base_url
        self.nasa_power_base_url = nasa_power_base_url
        self.overpass_base_url = overpass_base_url

    def repair(self, workspace_root: Path, need: dict[str, str]) -> list[dict[str, str]]:
        target = need.get("target_dataset", "").lower()
        if "population" in target:
            return [self._worldbank_population(workspace_root)]
        return []

    def _worldbank_population(self, workspace_root: Path) -> dict[str, str]:
        source = WorldBankProvider(workspace_root / "data").fetch_indicator(
            "all",
            "SP.POP.TOTL",
        )
        local_path = Path(source.local_path or "")
        try:
            relative_local_path = str(local_path.relative_to(workspace_root))
        except ValueError:
            relative_local_path = str(local_path)
        return {
            "source_id": source.source_id,
            "title": source.title,
            "url": source.url,
            "license": source.license,
            "provider": source.provider,
            "local_path": relative_local_path,
        }
