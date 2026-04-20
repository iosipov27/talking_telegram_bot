from __future__ import annotations

import unittest
from json import loads

import httpx

from talking_telegram_bot.clients.wttr_client import WttrClient, WttrClientError


class WttrClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_weather_requests_json_for_location(self) -> None:
        captured_query = ""
        captured_params = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_query
            captured_query = str(request.url)
            captured_params.update(request.url.params)
            return httpx.Response(
                200,
                json={
                    "current_condition": [
                        {
                            "FeelsLikeC": "11",
                            "FeelsLikeF": "51",
                            "humidity": "47",
                            "localObsDateTime": "2026-04-20 08:29 PM",
                            "temp_C": "12",
                            "temp_F": "54",
                            "visibility": "10",
                            "weatherDesc": [{"value": "Patchy rain nearby"}],
                            "winddir16Point": "NE",
                            "windspeedKmph": "14",
                            "windspeedMiles": "9",
                        },
                    ],
                    "nearest_area": [
                        {
                            "areaName": [{"value": "Nine Elms"}],
                            "country": [{"value": "United Kingdom"}],
                            "region": [{"value": "Wandsworth Greater London"}],
                        },
                    ],
                    "weather": [
                        {
                            "date": "2026-04-20",
                            "mintempC": "7",
                            "maxtempC": "15",
                            "mintempF": "45",
                            "maxtempF": "59",
                            "astronomy": [
                                {
                                    "sunrise": "05:55 AM",
                                    "sunset": "08:05 PM",
                                },
                            ],
                            "hourly": [
                                {
                                    "time": "1200",
                                    "weatherDesc": [{"value": "Sunny"}],
                                },
                            ],
                        },
                    ],
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = WttrClient(
            base_url="https://wttr.in",
            timeout_seconds=10,
            http_client=http_client,
        )

        response = await client.get_weather("New York")

        self.assertIn("/New+York", captured_query)
        self.assertEqual(captured_params["format"], "j1")
        self.assertEqual(response.requested_location, "New York")
        self.assertEqual(response.resolved_location, "Nine Elms")
        self.assertEqual(response.condition, "Patchy rain nearby")
        self.assertEqual(response.forecast[0].condition, "Sunny")
        await http_client.aclose()

    async def test_get_weather_raises_for_invalid_payload(self) -> None:
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"current_condition": []},
                ),
            ),
        )
        client = WttrClient(
            base_url="https://wttr.in",
            timeout_seconds=10,
            http_client=http_client,
        )

        with self.assertRaises(WttrClientError):
            await client.get_weather("London")

        await http_client.aclose()

