from __future__ import annotations

from datetime import UTC, datetime

import httpx

from mcm_agent.core.models import SourceRecord


class OpenAlexProvider:
    def search_works(self, query: str, max_results: int = 5) -> list[SourceRecord]:
        response = httpx.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": max_results},
            timeout=60,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"OpenAlex search failed: {response.status_code}")
        sources: list[SourceRecord] = []
        for item in response.json().get("results", []):
            title = item.get("display_name", "")
            url = item.get("doi") or item.get("id", "")
            sources.append(
                SourceRecord(
                    source_id=item.get("id", url).split("/")[-1],
                    title=title,
                    url=url,
                    accessed_at=datetime.now(UTC),
                    license="academic metadata",
                    provider="openalex",
                    source_rank="academic",
                    used_for="method background",
                    citation=title,
                )
            )
        return sources
