from dataclasses import replace

from talking_telegram_bot.clients.wttr_client import WttrClient, WttrClientError
from talking_telegram_bot.models.weather import WeatherResponse
from talking_telegram_bot.services.location_normalization_service import (
    LocationNormalizationError,
    LocationNormalizationService,
)


class WeatherServiceError(RuntimeError):
    """Raised when weather lookup can not be completed safely."""


class WeatherService:
    def __init__(
        self,
        wttr_client: WttrClient,
        location_normalization_service: LocationNormalizationService | None = None,
    ) -> None:
        self._wttr_client = wttr_client
        self._location_normalization_service = location_normalization_service

    async def get_weather(self, raw_location: str) -> WeatherResponse:
        location = raw_location.strip()
        if not location:
            raise WeatherServiceError("Weather location is empty.")
        lookup_location = location
        resolved_location = None
        if self._location_normalization_service is not None:
            try:
                normalized_location = await self._location_normalization_service.normalize(
                    location,
                )
            except LocationNormalizationError as exc:
                raise WeatherServiceError("Weather lookup is unavailable.") from exc
            lookup_location = normalized_location.lookup_query
            resolved_location = normalized_location.english_name
        try:
            weather_response = await self._wttr_client.get_weather(lookup_location)
        except WttrClientError as exc:
            raise WeatherServiceError("Weather lookup is unavailable.") from exc
        if resolved_location is not None:
            return replace(
                weather_response,
                requested_location=resolved_location,
                resolved_location=resolved_location,
            )
        return weather_response
