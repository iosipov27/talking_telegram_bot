from talking_telegram_bot.clients.wttr_client import WttrClient, WttrClientError
from talking_telegram_bot.models.weather import WeatherResponse


class WeatherServiceError(RuntimeError):
    """Raised when weather lookup can not be completed safely."""


class WeatherService:
    def __init__(self, wttr_client: WttrClient) -> None:
        self._wttr_client = wttr_client

    async def get_weather(self, raw_location: str) -> WeatherResponse:
        location = raw_location.strip()
        if not location:
            raise WeatherServiceError("Weather location is empty.")
        try:
            return await self._wttr_client.get_weather(location)
        except WttrClientError as exc:
            raise WeatherServiceError("Weather lookup is unavailable.") from exc

