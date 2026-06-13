from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float | None = None


class ExtractedPage(BaseModel):
    url: str
    title: str
    markdown: str
    metadata: dict[str, object] = Field(default_factory=dict)


class SearchProvider(Protocol):
    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class ExtractProvider(Protocol):
    def extract(self, url: str) -> ExtractedPage:
        raise NotImplementedError


class TavilyProvider:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=60,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Tavily search failed: {response.status_code}")
        payload = response.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content") or item.get("snippet", ""),
                score=item.get("score"),
            )
            for item in payload.get("results", [])
        ]


class FirecrawlProvider:
    def __init__(self, api_key: str, output_dir: Path) -> None:
        self.api_key = api_key
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def extract(self, url: str) -> ExtractedPage:
        response = httpx.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]},
            timeout=60,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Firecrawl scrape failed: {response.status_code}")
        payload = response.json()
        data = payload.get("data", payload)
        markdown = data.get("markdown", "")
        metadata = data.get("metadata", {})
        title = metadata.get("title", url)
        self._counter += 1
        output = self.output_dir / f"source_{self._counter:03d}.md"
        output.write_text(markdown, encoding="utf-8")
        return ExtractedPage(url=url, title=title, markdown=markdown, metadata=metadata)
