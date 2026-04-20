from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from talking_telegram_bot.clients.nominatim_client import (
    NominatimClient,
    NominatimClientError,
)


class NominatimClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_normalize_location_reads_english_name_and_coordinates(self) -> None:
        http_client = AsyncMock()
        response = Mock()
        response.json.return_value = [
            {
                "name": "Rome",
                "lat": "41.8933203",
                "lon": "12.4829321",
            },
        ]
        response.raise_for_status.return_value = None
        http_client.get.return_value = response
        client = NominatimClient(
            base_url="https://nominatim.example",
            timeout_seconds=10.0,
            user_agent="talking_telegram_bot/1.0",
            http_client=http_client,
        )

        result = await client.normalize_location("Рим")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.english_name, "Rome")
        self.assertEqual(result.lookup_query, "41.8933203,12.4829321")
        http_client.get.assert_awaited_once_with(
            "https://nominatim.example/search",
            params={
                "q": "Рим",
                "format": "jsonv2",
                "limit": "1",
                "accept-language": "en",
            },
            headers={"User-Agent": "talking_telegram_bot/1.0"},
        )

    async def test_normalize_location_returns_none_when_not_found(self) -> None:
        http_client = AsyncMock()
        response = Mock()
        response.json.return_value = []
        response.raise_for_status.return_value = None
        http_client.get.return_value = response
        client = NominatimClient(
            base_url="https://nominatim.example",
            timeout_seconds=10.0,
            user_agent="talking_telegram_bot/1.0",
            http_client=http_client,
        )

        result = await client.normalize_location("Unknown City")

        self.assertIsNone(result)

    async def test_normalize_location_raises_for_invalid_payload(self) -> None:
        http_client = AsyncMock()
        response = Mock()
        response.json.return_value = {"unexpected": "payload"}
        response.raise_for_status.return_value = None
        http_client.get.return_value = response
        client = NominatimClient(
            base_url="https://nominatim.example",
            timeout_seconds=10.0,
            user_agent="talking_telegram_bot/1.0",
            http_client=http_client,
        )

        with self.assertRaises(NominatimClientError):
            await client.normalize_location("Рим")
