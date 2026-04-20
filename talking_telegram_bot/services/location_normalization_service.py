from __future__ import annotations

import asyncio
import re

from talking_telegram_bot.clients.nominatim_client import (
    NominatimClient,
    NominatimClientError,
)
from talking_telegram_bot.models.location import NormalizedLocation

_CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁё]")


class LocationNormalizationError(RuntimeError):
    """Raised when a location can not be normalized safely."""


class LocationNormalizationService:
    def __init__(
        self,
        nominatim_client: NominatimClient,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._nominatim_client = nominatim_client
        self._retry_delay_seconds = retry_delay_seconds
        self._cache: dict[str, NormalizedLocation] = {}

    async def normalize(self, raw_location: str) -> NormalizedLocation:
        location = raw_location.strip()
        if not location:
            raise LocationNormalizationError("Location is empty.")
        cache_key = location.casefold()
        cached_location = self._cache.get(cache_key)
        if cached_location is not None:
            return cached_location
        candidates = self._build_candidates(location)
        for index, candidate in enumerate(candidates):
            try:
                normalized_location = await self._nominatim_client.normalize_location(
                    candidate,
                )
            except NominatimClientError as exc:
                raise LocationNormalizationError(
                    "Location normalization is unavailable.",
                ) from exc
            if normalized_location is not None:
                self._cache[cache_key] = normalized_location
                return normalized_location
            if index < len(candidates) - 1 and self._retry_delay_seconds > 0:
                await asyncio.sleep(self._retry_delay_seconds)
        if not self._contains_cyrillic(location):
            fallback_location = NormalizedLocation(
                english_name=location,
                lookup_query=location,
            )
            self._cache[cache_key] = fallback_location
            return fallback_location
        raise LocationNormalizationError("Location could not be normalized.")

    def _build_candidates(self, location: str) -> list[str]:
        variants: list[str] = []
        if self._contains_cyrillic(location):
            normalized_variants = self._build_russian_variants(location)
            variants.extend(normalized_variants)
        variants.append(location)
        return self._unique(variants)

    def _build_russian_variants(self, location: str) -> list[str]:
        parts = location.split()
        if not parts:
            return []
        last_part = parts[-1]
        lower_last_part = last_part.lower()
        candidates: list[str] = []
        if lower_last_part.endswith("ии") and len(last_part) > 2:
            candidates.append(self._replace_last_part(parts, f"{last_part[:-2]}ия"))
        elif lower_last_part.endswith("ы") and len(last_part) > 1:
            candidates.append(self._replace_last_part(parts, f"{last_part[:-1]}а"))
        elif lower_last_part.endswith("е") and len(last_part) > 1:
            stem = last_part[:-1]
            candidates.append(self._replace_last_part(parts, stem))
            candidates.append(self._replace_last_part(parts, f"{stem}а"))
        return candidates

    def _replace_last_part(self, parts: list[str], replacement: str) -> str:
        return " ".join([*parts[:-1], replacement])

    def _contains_cyrillic(self, value: str) -> bool:
        return _CYRILLIC_PATTERN.search(value) is not None

    def _unique(self, values: list[str]) -> list[str]:
        unique_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized_value = value.casefold()
            if normalized_value in seen:
                continue
            seen.add(normalized_value)
            unique_values.append(value)
        return unique_values
