from dataclasses import dataclass


@dataclass(frozen=True)
class SearchWebResult:
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class SearchWebResponse:
    query: str
    results: list[SearchWebResult]

