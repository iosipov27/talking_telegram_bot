from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.models.location import NormalizedLocation
from talking_telegram_bot.services.location_normalization_service import (
    LocationNormalizationError,
    LocationNormalizationService,
)


class LocationNormalizationServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_normalize_uses_russian_variants_before_original(self) -> None:
        nominatim_client = AsyncMock()
        nominatim_client.normalize_location.side_effect = [
            None,
            NormalizedLocation(
                english_name="Moscow",
                lookup_query="55.7504461,37.6174943",
            ),
        ]
        service = LocationNormalizationService(
            nominatim_client,
            retry_delay_seconds=0.0,
        )

        result = await service.normalize("Москве")

        self.assertEqual(result.english_name, "Moscow")
        self.assertEqual(result.lookup_query, "55.7504461,37.6174943")
        self.assertEqual(
            [call.args[0] for call in nominatim_client.normalize_location.await_args_list],
            ["Москв", "Москва"],
        )

    async def test_normalize_returns_ascii_location_when_geocoder_has_no_match(self) -> None:
        nominatim_client = AsyncMock()
        nominatim_client.normalize_location.return_value = None
        service = LocationNormalizationService(
            nominatim_client,
            retry_delay_seconds=0.0,
        )

        result = await service.normalize("New York")

        self.assertEqual(result.english_name, "New York")
        self.assertEqual(result.lookup_query, "New York")

    async def test_normalize_raises_when_cyrillic_location_has_no_match(self) -> None:
        nominatim_client = AsyncMock()
        nominatim_client.normalize_location.return_value = None
        service = LocationNormalizationService(
            nominatim_client,
            retry_delay_seconds=0.0,
        )

        with self.assertRaises(LocationNormalizationError):
            await service.normalize("Риме")
