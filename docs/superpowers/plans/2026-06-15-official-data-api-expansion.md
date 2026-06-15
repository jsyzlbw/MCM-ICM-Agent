# Official Data API Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand official-data repair beyond the current World Bank example so search repair can satisfy common population, economic, weather/climate, census, road-network, and geospatial data needs through provider adapters.

**Architecture:** Keep `SearchDataAgent` as the integration point and keep live calls out of tests. Extend `mcm_agent.providers.data_apis` with small provider classes that save raw responses under `data/raw/`, normalize each hit into the existing official-data payload contract, and let `OfficialDataApiRepairProvider.repair()` choose providers by data-need keywords. Extend JSON config and provider status so keys/base URLs stay in `mcm_agent_config.local.json`.

**Tech Stack:** Python 3, `httpx`, Pydantic settings, existing `SourceRecord`/lineage models, pytest with `respx`, ruff.

---

## Task 1: Provider Configuration Contract

**Files:**
- Modify: `mcm_agent_config.example.json`
- Modify: `src/mcm_agent/config.py`
- Modify: `src/mcm_agent/providers/factory.py`
- Modify: `src/mcm_agent/cli.py`
- Test: `tests/test_config_json.py`

- [ ] **Step 1: Write failing config test**

Append assertions in `tests/test_config_json.py::test_load_settings_overlays_json_values_over_env_file`:

```python
assert settings.oecd_base_url == "https://oecd.example"
assert settings.undata_base_url == "https://undata.example"
assert settings.us_census_api_key == "json-census"
assert settings.us_census_base_url == "https://census.example"
assert settings.noaa_api_key == "json-noaa"
assert settings.noaa_base_url == "https://noaa.example"
assert settings.nasa_power_base_url == "https://nasa.example"
assert settings.overpass_base_url == "https://overpass.example"
```

Add matching keys inside the test JSON `official_data` object.

- [ ] **Step 2: Run red test**

Run:

```bash
pytest tests/test_config_json.py::test_load_settings_overlays_json_values_over_env_file -q
```

Expected: fail because the new settings fields do not exist.

- [ ] **Step 3: Extend settings and example JSON**

Add settings fields:

```python
oecd_base_url: str = "https://sdmx.oecd.org/public/rest/v1/data"
undata_base_url: str = "https://data.un.org/Handlers/DownloadHandler.ashx"
us_census_api_key: str = ""
us_census_base_url: str = "https://api.census.gov/data"
noaa_api_key: str = ""
noaa_base_url: str = "https://www.ncei.noaa.gov/cdo-web/api/v2"
nasa_power_base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
overpass_base_url: str = "https://overpass-api.de/api/interpreter"
```

Map each JSON key under `official_data`.

- [ ] **Step 4: Wire provider factory and status text**

Pass the new settings into `OfficialDataApiRepairProvider`. Update `provider-status` so it lists World Bank, Open-Meteo, NASA POWER, Overpass, OECD/UNData/Census/NOAA, and appends FRED/Census/NOAA only when keys are configured.

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest tests/test_config_json.py -q
```

Commit:

```bash
git add mcm_agent_config.example.json src/mcm_agent/config.py src/mcm_agent/providers/factory.py src/mcm_agent/cli.py tests/test_config_json.py
git commit -m "feat: extend official data configuration"
```

---

## Task 2: Provider Adapters And Payload Normalization

**Files:**
- Modify: `src/mcm_agent/providers/data_apis.py`
- Test: `tests/test_search_data.py`

- [ ] **Step 1: Write failing provider tests**

Add mocked tests proving:

```python
OECDProvider(tmp_path, base_url="https://sdmx.example").fetch_dataset("DF_POP", {"REF_AREA": "USA"})
UNDataProvider(tmp_path, base_url="https://undata.example").fetch_dataset("POP")
FredProvider(tmp_path, api_key="key").fetch_series("GDP")
USCensusProvider(tmp_path, api_key="key", base_url="https://census.example").fetch_dataset("2022/acs/acs5", {"get": "NAME,B01003_001E", "for": "state:*"})
NOAAProvider(tmp_path, api_key="key", base_url="https://noaa.example").fetch_data({"datasetid": "GHCND"})
NASAPowerProvider(tmp_path, base_url="https://nasa.example").fetch_point({"latitude": "39", "longitude": "-77", "parameters": "PRECTOTCORR"})
OpenMeteoProvider(tmp_path, base_url="https://weather.example/archive").fetch_archive({"latitude": "39", "longitude": "-77", "daily": "temperature_2m_max"})
OverpassProvider(tmp_path, base_url="https://overpass.example").fetch_query("[out:json];node(0,0,1,1);out;")
```

Each test asserts `source_rank == "official"`, a provider-specific `provider`, and a raw file under `data/raw/`.

- [ ] **Step 2: Run red tests**

Run:

```bash
pytest tests/test_search_data.py -q
```

Expected: fail because adapter classes are missing.

- [ ] **Step 3: Implement small adapters**

Create one class per provider. Each class should:

- Accept `workspace_data_dir` and provider base URL/API key.
- Perform one `httpx.get()` or `httpx.post()` call.
- Save the JSON/text body to `data/raw/<provider>_<slug>.json`.
- Return a `SourceRecord` with `source_rank="official"`, `provider=<provider_id>`, `local_path`, and a citation.

- [ ] **Step 4: Add helper for payload conversion**

Add a helper that turns `SourceRecord` into the existing official repair payload:

```python
def _payload_from_source(workspace_root: Path, source: SourceRecord) -> dict[str, str]:
    ...
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest tests/test_search_data.py -q
```

Commit:

```bash
git add src/mcm_agent/providers/data_apis.py tests/test_search_data.py
git commit -m "feat: add official data provider adapters"
```

---

## Task 3: Repair Routing Across Providers

**Files:**
- Modify: `src/mcm_agent/providers/data_apis.py`
- Modify: `src/mcm_agent/agents/search_data.py`
- Test: `tests/test_search_data.py`

- [ ] **Step 1: Write failing repair-routing tests**

Add tests for `OfficialDataApiRepairProvider.repair()`:

```python
assert provider.repair(tmp_path, {"target_dataset": "public population data"})[0]["provider"] == "world_bank_api"
assert provider.repair(tmp_path, {"target_dataset": "GDP economic indicators"})[0]["provider"] in {"world_bank_api", "oecd_api", "fred_api"}
assert provider.repair(tmp_path, {"target_dataset": "weather climate rainfall data"})[0]["provider"] in {"open_meteo_api", "nasa_power_api", "noaa_api"}
assert provider.repair(tmp_path, {"target_dataset": "US census population by state"})[0]["provider"] == "us_census_api"
assert provider.repair(tmp_path, {"target_dataset": "road network nodes edges"})[0]["provider"] == "overpass_api"
```

Use `respx` mocks for each HTTP request.

- [ ] **Step 2: Run red tests**

Run:

```bash
pytest tests/test_search_data.py::test_official_data_api_repair_provider_routes_multiple_data_needs -q
```

Expected: fail because repair only supports population via World Bank.

- [ ] **Step 3: Implement keyword router**

In `OfficialDataApiRepairProvider.repair()`:

- Prefer US Census for targets containing `us census`, `census`, or `state population`.
- Prefer Overpass for `road`, `network`, `nodes`, `edges`, `osm`, or `transport`.
- Prefer weather/climate providers for `weather`, `climate`, `rainfall`, `temperature`, `precipitation`.
- Prefer FRED when an API key exists and target contains `fred`, `gdp`, `inflation`, `economic`, or `unemployment`; otherwise use OECD or World Bank.
- Keep World Bank population fallback.

Catch provider exceptions and try the next candidate. Return an empty list only when all candidates fail or no route applies.

- [ ] **Step 4: Include attempted provider metadata in repair actions**

Extend `SearchDataAgent._repair_action()` output with `official_api_status` when provider attempts are available. Keep this optional so existing tests remain simple.

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest tests/test_search_data.py -q
```

Commit:

```bash
git add src/mcm_agent/providers/data_apis.py src/mcm_agent/agents/search_data.py tests/test_search_data.py
git commit -m "feat: route search repair to official APIs"
```

---

## Task 4: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/WORKFLOW.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update docs**

Document:

- Official data provider list: World Bank, OECD, UNData, FRED, US Census, NOAA, NASA POWER, Open-Meteo, OSM/Overpass.
- Which providers require API keys: FRED, US Census optional/recommended, NOAA token optional/required depending endpoint.
- No-key providers: World Bank, OECD public SDMX, UNData download, NASA POWER, Open-Meteo, Overpass.
- All provider credentials live under `official_data` in `mcm_agent_config.local.json`.
- Unit tests use mocked HTTP, not live APIs.

- [ ] **Step 2: Full verification**

Run:

```bash
pytest -q
ruff check src tests scripts
```

Expected: all pass.

- [ ] **Step 3: Commit and push**

Commit:

```bash
git add README.md docs/WORKFLOW.md docs/PROJECT_STATUS.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: describe official data api expansion"
git push origin main
```

---

## Acceptance Criteria

- JSON config exposes all official-data provider keys/base URLs without committing secrets.
- Official-data provider adapters save raw responses under `data/raw/` and return official `SourceRecord`s.
- Search repair can satisfy at least one mocked data need from population, economic, weather/climate, census, and road-network categories.
- Unit tests use fakes or `respx`; no live API calls run in pytest.
- Full verification passes:

```bash
pytest -q
ruff check src tests scripts
```

## Self-Review

- Spec coverage: covers config, provider adapters, repair routing, docs, and verification.
- Placeholder scan: clean.
- Type consistency: all providers return `SourceRecord`; repair integration keeps the existing `dict[str, str]` payload contract.
