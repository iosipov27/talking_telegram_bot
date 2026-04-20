from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.clients.wttr_client import WttrClientError
from talking_telegram_bot.models.weather import WeatherForecastDay, WeatherResponse
from talking_telegram_bot.services.weather_service import (
    WeatherService,
    WeatherServiceError,
)


class WeatherServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_weather_strips_location(self) -> None:
        wttr_client = AsyncMock()
        wttr_client.get_weather.return_value = WeatherResponse(
            requested_location="London",
            resolved_location="London",
            region="England",
            country="United Kingdom",
            observation_time="2026-04-20 08:29 PM",
            condition="Sunny",
            temp_c="12",
            temp_f="54",
            feels_like_c="11",
            feels_like_f="51",
            humidity="47",
            wind_speed_kmph="14",
            wind_speed_miles="9",
            wind_direction="NE",
            visibility_km="10",
            forecast=[
                WeatherForecastDay(
                    date="2026-04-20",
                    condition="Sunny",
                    min_temp_c="7",
                    max_temp_c="15",
                    min_temp_f="45",
                    max_temp_f="59",
                    sunrise="05:55 AM",
                    sunset="08:05 PM",
                ),
            ],
        )
        service = WeatherService(wttr_client)

        response = await service.get_weather("  London  ")

        self.assertEqual(response.resolved_location, "London")
        wttr_client.get_weather.assert_awaited_once_with("London")

    async def test_get_weather_raises_for_empty_location(self) -> None:
        service = WeatherService(AsyncMock())

        with self.assertRaises(WeatherServiceError):
            await service.get_weather("   ")

    async def test_get_weather_maps_client_error(self) -> None:
        wttr_client = AsyncMock()
        wttr_client.get_weather.side_effect = WttrClientError("down")
        service = WeatherService(wttr_client)

        with self.assertRaises(WeatherServiceError):
            await service.get_weather("London")

