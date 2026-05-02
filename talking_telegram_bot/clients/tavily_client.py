from __future__ import annotations

import logging
from typing import Any

import httpx

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.models.search import SearchWebResponse, SearchWebResult

logger = logging.getLogger(__name__)


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
        log_event(
            logger,
            logging.INFO,
            log_events.TAVILY_REQUEST_SENT,
            method="POST",
            endpoint="/search",
            query_length=len(query),
            max_results=max_results,
        )
        try:
            response = await self._http_client.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=self._build_payload(query, max_results),
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            self._log_request_failed("timeout")
            raise TavilyTimeoutError("Tavily request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            self._log_request_failed("http_status", status_code=exc.response.status_code)
            raise TavilyClientError("Tavily returned an unsuccessful status.") from exc
        except httpx.HTTPError as exc:
            self._log_request_failed("http_error")
            raise TavilyClientError("Tavily request failed.") from exc
        search_response = self._extract_response(self._read_json(response))
        log_event(
            logger,
            logging.INFO,
            log_events.TAVILY_RESPONSE_RECEIVED,
            status_code=response.status_code,
            result_count=len(search_response.results),
        )
        return search_response

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

    def _log_request_failed(self, reason: str, status_code: int | None = None) -> None:
        fields: dict[str, object] = {"reason": reason}
        if status_code is not None:
            fields["status_code"] = status_code
        log_event(
            logger,
            logging.ERROR,
            log_events.TAVILY_REQUEST_FAILED,
            **fields,
            exc_info=True,
        )
