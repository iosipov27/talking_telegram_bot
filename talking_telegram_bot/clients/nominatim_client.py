from __future__ import annotations

import logging
from typing import Any

import httpx

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.models.location import NormalizedLocation

logger = logging.getLogger(__name__)


class NominatimClientError(RuntimeError):
    """Raised when Nominatim request or response handling fails."""


class NominatimTimeoutError(NominatimClientError):
    """Raised when Nominatim does not respond in time."""


class NominatimClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        user_agent: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent.strip()
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def normalize_location(self, query: str) -> NormalizedLocation | None:
        url = f"{self._base_url}/search"
        log_event(
            logger,
            logging.INFO,
            log_events.NOMINATIM_REQUEST_SENT,
            method="GET",
            endpoint="/search",
            query_length=len(query),
        )
        try:
            response = await self._http_client.get(
                url,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": "1",
                    "accept-language": "en",
                },
                headers={"User-Agent": self._user_agent},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            self._log_request_failed("timeout")
            raise NominatimTimeoutError("Nominatim request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            self._log_request_failed("http_status", status_code=exc.response.status_code)
            raise NominatimClientError("Nominatim returned an unsuccessful status.") from exc
        except httpx.HTTPError as exc:
            self._log_request_failed("http_error")
            raise NominatimClientError("Nominatim request failed.") from exc
        location = self._extract_location(self._read_json(response))
        log_event(
            logger,
            logging.INFO,
            log_events.NOMINATIM_RESPONSE_RECEIVED,
            status_code=response.status_code,
            found=location is not None,
        )
        return location

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    def _read_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise NominatimClientError("Nominatim returned an invalid JSON payload.") from exc

    def _extract_location(self, data: Any) -> NormalizedLocation | None:
        if not isinstance(data, list):
            raise NominatimClientError("Nominatim returned an invalid response payload.")
        if not data:
            return None
        first_item = data[0]
        if not isinstance(first_item, dict):
            raise NominatimClientError("Nominatim returned an invalid response payload.")
        english_name = self._read_name(first_item)
        latitude = self._read_required_text(first_item, "lat")
        longitude = self._read_required_text(first_item, "lon")
        return NormalizedLocation(
            english_name=english_name,
            lookup_query=f"{latitude},{longitude}",
        )

    def _read_name(self, item: dict[str, Any]) -> str:
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        display_name = self._read_required_text(item, "display_name")
        return display_name.split(",", maxsplit=1)[0].strip()

    def _read_required_text(self, data: dict[str, Any], field_name: str) -> str:
        value = data.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise NominatimClientError(f"Nominatim returned an invalid {field_name} payload.")

    def _log_request_failed(self, reason: str, status_code: int | None = None) -> None:
        fields: dict[str, object] = {"reason": reason}
        if status_code is not None:
            fields["status_code"] = status_code
        log_event(
            logger,
            logging.ERROR,
            log_events.NOMINATIM_REQUEST_FAILED,
            **fields,
            exc_info=True,
        )
