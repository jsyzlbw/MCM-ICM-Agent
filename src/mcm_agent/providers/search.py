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


class BraveSearchProvider:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
            params={
                "q": query,
                "count": min(max_results, 20),
                "result_filter": "web",
                "safesearch": "moderate",
            },
            timeout=60,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Brave search failed: {response.status_code}")
        payload = response.json()
        web = payload.get("web") or {}
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description") or item.get("snippet", ""),
                score=None,
            )
            for item in web.get("results", [])
        ]


class ExaSearchProvider:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        response = httpx.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "query": query,
                "numResults": max_results,
                "contents": {"highlights": True, "text": True},
            },
            timeout=60,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Exa search failed: {response.status_code}")
        payload = response.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=self._snippet(item),
                score=item.get("score"),
            )
            for item in payload.get("results", [])
        ]

    def _snippet(self, item: dict[str, object]) -> str:
        highlights = item.get("highlights")
        if isinstance(highlights, list) and highlights:
            return str(highlights[0])
        return str(item.get("text") or item.get("summary") or "")


class FallbackSearchProvider:
    def __init__(self, providers: list[SearchProvider]) -> None:
        self.providers = providers

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                results = provider.search(query, max_results=max_results)
            except Exception as exc:
                errors.append(f"{provider.__class__.__name__}: {exc}")
                continue
            if results:
                return results
        if errors:
            raise RuntimeError("All search providers failed: " + "; ".join(errors))
        return []


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
