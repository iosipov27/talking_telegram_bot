from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedLocation:
    english_name: str
    lookup_query: str
