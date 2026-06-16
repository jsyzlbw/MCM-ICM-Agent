from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderResult:
    content: str
    metadata: dict[str, object]


class TextGenerationProvider(Protocol):
    def generate(self, system: str, prompt: str, *, temperature: float = 0.2) -> ProviderResult:
        raise NotImplementedError


@dataclass(frozen=True)
class ProviderBundle:
    llm: TextGenerationProvider
    mineru: object
    search: object
    extractor: object
    official_data: object
    humanizer: object
    latex: object
    embedding: object | None = None
    reranker: object | None = None
