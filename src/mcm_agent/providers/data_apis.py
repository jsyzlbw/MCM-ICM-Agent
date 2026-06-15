from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from mcm_agent.core.models import SourceRecord


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return slug or "dataset"


def _write_raw(data_dir: Path, provider: str, slug: str, payload: object) -> Path:
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{provider}_{_slug(slug)}.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _official_source(
    *,
    source_id: str,
    title: str,
    url: str,
    provider: str,
    license_name: str,
    used_for: str,
    citation: str,
    local_path: Path,
) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        title=title,
        url=url,
        accessed_at=datetime.now(UTC),
        license=license_name,
        provider=provider,
        source_rank="official",
        used_for=used_for,
        citation=citation,
        local_path=str(local_path),
    )


def _payload_from_source(workspace_root: Path, source: SourceRecord) -> dict[str, str]:
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


class OECDProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        base_url: str = "https://sdmx.oecd.org/public/rest/v1/data",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.base_url = base_url.rstrip("/")

    def fetch_dataset(self, dataset: str, params: dict[str, str] | None = None) -> SourceRecord:
        response = httpx.get(f"{self.base_url}/{dataset}", params=params or {}, timeout=60)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"OECD fetch failed: {response.status_code}")
        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        local_path = _write_raw(self.data_dir, "oecd", dataset, payload)
        return _official_source(
            source_id=f"oecd_{_slug(dataset)}",
            title=f"OECD {dataset} dataset",
            url=str(response.url),
            provider="oecd_api",
            license_name="OECD data terms",
            used_for="official OECD data repair",
            citation="OECD Data Explorer",
            local_path=local_path,
        )


class UNDataProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        base_url: str = "https://data.un.org/Handlers/DownloadHandler.ashx",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.base_url = base_url

    def fetch_dataset(self, dataset: str) -> SourceRecord:
        response = httpx.get(self.base_url, params={"DataFilter": dataset}, timeout=60)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"UNData fetch failed: {response.status_code}")
        local_path = _write_raw(self.data_dir, "undata", dataset, response.text)
        return _official_source(
            source_id=f"undata_{_slug(dataset)}",
            title=f"UNData {dataset} dataset",
            url=str(response.url),
            provider="undata_api",
            license_name="UNData terms of use",
            used_for="official UN data repair",
            citation="United Nations Data",
            local_path=local_path,
        )


class FredProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        api_key: str,
        base_url: str = "https://api.stlouisfed.org/fred/series/observations",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.api_key = api_key
        self.base_url = base_url

    def fetch_series(self, series_id: str) -> SourceRecord:
        response = httpx.get(
            self.base_url,
            params={"series_id": series_id, "api_key": self.api_key, "file_type": "json"},
            timeout=60,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"FRED fetch failed: {response.status_code}")
        local_path = _write_raw(self.data_dir, "fred", series_id, response.json())
        return _official_source(
            source_id=f"fred_{_slug(series_id)}",
            title=f"FRED {series_id} series",
            url=str(response.url),
            provider="fred_api",
            license_name="FRED terms of use",
            used_for="official economic data repair",
            citation="Federal Reserve Economic Data",
            local_path=local_path,
        )


class USCensusProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        api_key: str = "",
        base_url: str = "https://api.census.gov/data",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def fetch_dataset(self, dataset: str, params: dict[str, str]) -> SourceRecord:
        request_params = dict(params)
        if self.api_key:
            request_params["key"] = self.api_key
        response = httpx.get(f"{self.base_url}/{dataset}", params=request_params, timeout=60)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"US Census fetch failed: {response.status_code}")
        local_path = _write_raw(self.data_dir, "us_census", dataset, response.json())
        return _official_source(
            source_id=f"us_census_{_slug(dataset)}",
            title=f"US Census {dataset} dataset",
            url=str(response.url),
            provider="us_census_api",
            license_name="US Census public data",
            used_for="official census data repair",
            citation="United States Census Bureau",
            local_path=local_path,
        )


class NOAAProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        api_key: str = "",
        base_url: str = "https://www.ncei.noaa.gov/cdo-web/api/v2",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def fetch_data(self, params: dict[str, str]) -> SourceRecord:
        headers = {"token": self.api_key} if self.api_key else {}
        response = httpx.get(f"{self.base_url}/data", params=params, headers=headers, timeout=60)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"NOAA fetch failed: {response.status_code}")
        slug = params.get("datasetid") or params.get("datatypeid") or "data"
        local_path = _write_raw(self.data_dir, "noaa", slug, response.json())
        return _official_source(
            source_id=f"noaa_{_slug(slug)}",
            title=f"NOAA {slug} data",
            url=str(response.url),
            provider="noaa_api",
            license_name="NOAA public data",
            used_for="official climate data repair",
            citation="NOAA Climate Data Online",
            local_path=local_path,
        )


class NASAPowerProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.base_url = base_url

    def fetch_point(self, params: dict[str, str]) -> SourceRecord:
        request_params = {"format": "JSON", "community": "AG", **params}
        response = httpx.get(self.base_url, params=request_params, timeout=60)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"NASA POWER fetch failed: {response.status_code}")
        slug = params.get("parameters", "point")
        local_path = _write_raw(self.data_dir, "nasa_power", slug, response.json())
        return _official_source(
            source_id=f"nasa_power_{_slug(slug)}",
            title=f"NASA POWER {slug} data",
            url=str(response.url),
            provider="nasa_power_api",
            license_name="NASA POWER public data",
            used_for="official climate data repair",
            citation="NASA POWER Project",
            local_path=local_path,
        )


class OpenMeteoProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        base_url: str = "https://archive-api.open-meteo.com/v1/archive",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.base_url = base_url

    def fetch_archive(self, params: dict[str, str]) -> SourceRecord:
        response = httpx.get(self.base_url, params=params, timeout=60)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Open-Meteo fetch failed: {response.status_code}")
        slug = params.get("daily") or params.get("hourly") or "archive"
        local_path = _write_raw(self.data_dir, "open_meteo", slug, response.json())
        return _official_source(
            source_id=f"open_meteo_{_slug(slug)}",
            title=f"Open-Meteo {slug} archive",
            url=str(response.url),
            provider="open_meteo_api",
            license_name="Open-Meteo terms",
            used_for="official weather data repair",
            citation="Open-Meteo Historical Weather API",
            local_path=local_path,
        )


class OverpassProvider:
    def __init__(
        self,
        workspace_data_dir: Path,
        *,
        base_url: str = "https://overpass-api.de/api/interpreter",
    ) -> None:
        self.data_dir = workspace_data_dir
        self.base_url = base_url

    def fetch_query(self, query: str) -> SourceRecord:
        response = httpx.post(self.base_url, data={"data": query}, timeout=60)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Overpass fetch failed: {response.status_code}")
        local_path = _write_raw(self.data_dir, "overpass", "query", response.json())
        return _official_source(
            source_id="overpass_query",
            title="OpenStreetMap Overpass query result",
            url=str(response.url),
            provider="overpass_api",
            license_name="OpenStreetMap ODbL",
            used_for="official/open geospatial data repair",
            citation="OpenStreetMap contributors via Overpass API",
            local_path=local_path,
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
        for repair in self._repair_candidates(target):
            try:
                return [repair(workspace_root)]
            except Exception:
                continue
        return []

    def _repair_candidates(self, target: str):
        candidates = []
        if any(keyword in target for keyword in ["census", "state population"]):
            candidates.append(self._us_census_population)
        if any(
            keyword in target
            for keyword in ["road", "network", "nodes", "edges", "osm", "transport"]
        ):
            candidates.append(self._overpass_roads)
        if any(
            keyword in target
            for keyword in ["weather", "climate", "rainfall", "temperature", "precipitation"]
        ):
            candidates.extend([self._open_meteo_weather, self._nasa_power_weather])
            if self.noaa_api_key:
                candidates.append(self._noaa_weather)
        if any(
            keyword in target
            for keyword in ["fred", "gdp", "inflation", "economic", "unemployment"]
        ):
            if self.fred_api_key:
                candidates.append(self._fred_gdp)
            candidates.extend([self._oecd_economic, self._worldbank_gdp])
        if "population" in target:
            candidates.append(self._worldbank_population)
        return candidates

    def _worldbank_population(self, workspace_root: Path) -> dict[str, str]:
        source = WorldBankProvider(workspace_root / "data").fetch_indicator(
            "all",
            "SP.POP.TOTL",
        )
        return _payload_from_source(workspace_root, source)

    def _worldbank_gdp(self, workspace_root: Path) -> dict[str, str]:
        source = WorldBankProvider(workspace_root / "data").fetch_indicator(
            "all",
            "NY.GDP.MKTP.CD",
        )
        return _payload_from_source(workspace_root, source)

    def _fred_gdp(self, workspace_root: Path) -> dict[str, str]:
        source = FredProvider(workspace_root / "data", api_key=self.fred_api_key).fetch_series("GDP")
        return _payload_from_source(workspace_root, source)

    def _oecd_economic(self, workspace_root: Path) -> dict[str, str]:
        source = OECDProvider(
            workspace_root / "data",
            base_url=self.oecd_base_url,
        ).fetch_dataset("DF_DP_LIVE", {"MEASURE": "GDP"})
        return _payload_from_source(workspace_root, source)

    def _us_census_population(self, workspace_root: Path) -> dict[str, str]:
        source = USCensusProvider(
            workspace_root / "data",
            api_key=self.us_census_api_key,
            base_url=self.us_census_base_url,
        ).fetch_dataset(
            "2022/acs/acs5",
            {"get": "NAME,B01003_001E", "for": "state:*"},
        )
        return _payload_from_source(workspace_root, source)

    def _open_meteo_weather(self, workspace_root: Path) -> dict[str, str]:
        source = OpenMeteoProvider(
            workspace_root / "data",
            base_url=self.open_meteo_base_url,
        ).fetch_archive(
            {
                "latitude": "39",
                "longitude": "-77",
                "start_date": "2023-01-01",
                "end_date": "2023-01-07",
                "daily": "precipitation_sum",
            }
        )
        return _payload_from_source(workspace_root, source)

    def _nasa_power_weather(self, workspace_root: Path) -> dict[str, str]:
        source = NASAPowerProvider(
            workspace_root / "data",
            base_url=self.nasa_power_base_url,
        ).fetch_point(
            {
                "latitude": "39",
                "longitude": "-77",
                "start": "20230101",
                "end": "20230107",
                "parameters": "PRECTOTCORR",
            }
        )
        return _payload_from_source(workspace_root, source)

    def _noaa_weather(self, workspace_root: Path) -> dict[str, str]:
        source = NOAAProvider(
            workspace_root / "data",
            api_key=self.noaa_api_key,
            base_url=self.noaa_base_url,
        ).fetch_data({"datasetid": "GHCND"})
        return _payload_from_source(workspace_root, source)

    def _overpass_roads(self, workspace_root: Path) -> dict[str, str]:
        source = OverpassProvider(
            workspace_root / "data",
            base_url=self.overpass_base_url,
        ).fetch_query("[out:json];way[highway](0,0,1,1);out body;")
        return _payload_from_source(workspace_root, source)
