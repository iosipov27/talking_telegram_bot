from __future__ import annotations

from typing import Any

import httpx

from talking_telegram_bot.models.search import SearchWebResponse, SearchWebResult


class TavilyClientError(RuntimeError):
    """Raised when Tavily request or response handling fails."""


class TavilyTimeoutError(TavilyClientError):
    """Raised when Tavily does not respond in time."""


class TavilyClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def search(self, query: str, max_results: int) -> SearchWebResponse:
        url = f"{self._base_url}/search"
        try:
            response = await self._http_client.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=self._build_payload(query, max_results),
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TavilyTimeoutError("Tavily request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise TavilyClientError("Tavily returned an unsuccessful status.") from exc
        except httpx.HTTPError as exc:
            raise TavilyClientError("Tavily request failed.") from exc
        return self._extract_response(self._read_json(response))

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    def _build_payload(self, query: str, max_results: int) -> dict[str, Any]:
        return {
            "query": query,
            "topic": "general",
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }

    def _read_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise TavilyClientError("Tavily returned an invalid JSON payload.") from exc

    def _extract_response(self, data: Any) -> SearchWebResponse:
        if not isinstance(data, dict):
            raise TavilyClientError("Tavily returned an invalid response payload.")
        query = data.get("query")
        results = data.get("results")
        if not isinstance(query, str) or not isinstance(results, list):
            raise TavilyClientError("Tavily returned an invalid response payload.")
        return SearchWebResponse(
            query=query,
            results=[self._extract_result(item) for item in results],
        )

    def _extract_result(self, item: Any) -> SearchWebResult:
        if not isinstance(item, dict):
            raise TavilyClientError("Tavily returned an invalid result payload.")
        title = item.get("title")
        url = item.get("url")
        content = item.get("content")
        if not all(isinstance(value, str) for value in (title, url, content)):
            raise TavilyClientError("Tavily returned an invalid result payload.")
        return SearchWebResult(
            title=title,
            url=url,
            content=content,
        )

