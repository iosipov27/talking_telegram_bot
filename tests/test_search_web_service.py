from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.clients.tavily_client import TavilyClientError
from talking_telegram_bot.models.search import SearchWebResponse, SearchWebResult
from talking_telegram_bot.services.search_web_service import (
    SearchWebService,
    SearchWebServiceError,
)


class SearchWebServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_search_web_strips_query(self) -> None:
        tavily_client = AsyncMock()
        tavily_client.search.return_value = SearchWebResponse(
            query="python",
            results=[
                SearchWebResult(
                    title="Python",
                    url="https://example.com",
                    content="Language",
                ),
            ],
        )
        service = SearchWebService(tavily_client)

        response = await service.search_web("  python  ")

        self.assertEqual(response.query, "python")
        tavily_client.search.assert_awaited_once_with("python", 5)

    async def test_search_web_raises_for_empty_query(self) -> None:
        service = SearchWebService(AsyncMock())

        with self.assertRaises(SearchWebServiceError):
            await service.search_web("   ")

    async def test_search_web_maps_client_error(self) -> None:
        tavily_client = AsyncMock()
        tavily_client.search.side_effect = TavilyClientError("down")
        service = SearchWebService(tavily_client)

        with self.assertRaises(SearchWebServiceError):
            await service.search_web("python")

