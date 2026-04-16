from __future__ import annotations

import unittest
from json import loads

import httpx

from talking_telegram_bot.clients.tavily_client import TavilyClient, TavilyClientError


class TavilyClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_search_sends_expected_payload_and_headers(self) -> None:
        captured_authorization = ""
        captured_payload = {}

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_authorization
            captured_authorization = request.headers["Authorization"]
            captured_payload.update(loads(request.content))
            return httpx.Response(
                200,
                json={
                    "query": "python",
                    "results": [
                        {
                            "title": "Python",
                            "url": "https://example.com",
                            "content": "Language",
                        },
                    ],
                },
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = TavilyClient(
            api_key="tvly-secret",
            base_url="https://api.tavily.com",
            timeout_seconds=10,
            http_client=http_client,
        )

        response = await client.search("python", 3)

        self.assertEqual(captured_authorization, "Bearer tvly-secret")
        self.assertEqual(captured_payload["query"], "python")
        self.assertEqual(captured_payload["max_results"], 3)
        self.assertEqual(response.results[0].title, "Python")
        await http_client.aclose()

    async def test_search_raises_for_invalid_payload(self) -> None:
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"query": "python"}),
            ),
        )
        client = TavilyClient(
            api_key="tvly-secret",
            base_url="https://api.tavily.com",
            timeout_seconds=10,
            http_client=http_client,
        )

        with self.assertRaises(TavilyClientError):
            await client.search("python", 3)

        await http_client.aclose()
