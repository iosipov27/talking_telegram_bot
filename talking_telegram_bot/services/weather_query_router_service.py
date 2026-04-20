from __future__ import annotations

from dataclasses import dataclass
import re

_WEATHER_KEYWORDS = (
    "погод",
    "температур",
    "осадк",
    "дожд",
    "снег",
    "ветер",
    "прогноз",
    "weather",
    "temperature",
    "forecast",
    "rain",
    "snow",
    "wind",
)
_DATE_PATTERNS = (
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    r"\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b",
    r"\b\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b",
    r"\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\b(?:сегодня|завтра|послезавтра|вчера|понедельник|вторник|среда|четверг|пятница|суббота|воскресенье)\b",
    r"\b(?:today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|next week)\b",
    r"\bчерез\s+\d+\s+(?:дн|дня|дней|неделю|недели|недель)\b",
)
_LOCATION_PATTERNS = (
    r"\b(?:в|во|in|for)\s+(?P<location>[^?!.,]+)$",
    r"\b(?:для)\s+(?P<location>[^?!.,]+)$",
    r"^(?:weather|forecast)\s+(?P<location>[^?!.,]+)$",
    r"^(?:погода|прогноз)\s+(?P<location>[^?!.,]+)$",
)


@dataclass(frozen=True, slots=True)
class WeatherQueryRoute:
    should_route: bool
    location: str | None = None


class WeatherQueryRouterService:
    def route(self, raw_text: str) -> WeatherQueryRoute:
        normalized_text = raw_text.strip()
        normalized_text = normalized_text.rstrip("?!., ")
        lowered_text = normalized_text.lower()
        if not self._looks_like_weather_query(lowered_text):
            return WeatherQueryRoute(should_route=False)
        if self._contains_date_reference(lowered_text):
            return WeatherQueryRoute(should_route=False)
        return WeatherQueryRoute(
            should_route=True,
            location=self._extract_location(normalized_text),
        )

    def _looks_like_weather_query(self, lowered_text: str) -> bool:
        return any(keyword in lowered_text for keyword in _WEATHER_KEYWORDS)

    def _contains_date_reference(self, lowered_text: str) -> bool:
        return any(
            re.search(pattern, lowered_text, flags=re.IGNORECASE)
            for pattern in _DATE_PATTERNS
        )

    def _extract_location(self, text: str) -> str | None:
        search_text = text.rstrip("?!., ")
        for pattern in _LOCATION_PATTERNS:
            match = re.search(pattern, search_text, flags=re.IGNORECASE)
            if match is None:
                continue
            location = match.group("location").strip(" ?!.,")
            if location:
                return location
        return None
