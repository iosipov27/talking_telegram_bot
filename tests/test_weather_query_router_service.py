from __future__ import annotations

import unittest

from talking_telegram_bot.services.weather_query_router_service import (
    WeatherQueryRouterService,
)


class WeatherQueryRouterServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WeatherQueryRouterService()

    def test_routes_weather_query_without_date(self) -> None:
        route = self.service.route("Какая погода в Риме?")

        self.assertTrue(route.should_route)
        self.assertEqual(route.location, "Риме")

    def test_does_not_route_weather_query_with_explicit_date(self) -> None:
        route = self.service.route("Какая погода будет в Риме 30 апреля?")

        self.assertFalse(route.should_route)
        self.assertIsNone(route.location)

    def test_routes_weather_query_without_location_for_clarification(self) -> None:
        route = self.service.route("Какая погода?")

        self.assertTrue(route.should_route)
        self.assertIsNone(route.location)

    def test_does_not_route_non_weather_query(self) -> None:
        route = self.service.route("Кто президент Франции?")

        self.assertFalse(route.should_route)
        self.assertIsNone(route.location)

