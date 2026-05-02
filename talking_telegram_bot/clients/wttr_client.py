from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

import httpx

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.models.weather import WeatherForecastDay, WeatherResponse

logger = logging.getLogger(__name__)


class WttrClientError(RuntimeError):
    """Raised when wttr.in request or response handling fails."""


class WttrTimeoutError(WttrClientError):
    """Raised when wttr.in does not respond in time."""


class WttrClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def get_weather(self, location: str) -> WeatherResponse:
        encoded_location = quote_plus(location)
        url = f"{self._base_url}/{encoded_location}"
        log_event(
            logger,
            logging.INFO,
            log_events.WTTR_REQUEST_SENT,
            method="GET",
            endpoint="/{location}",
            location_length=len(location),
        )
        try:
            response = await self._http_client.get(
                url,
                params={"format": "j1"},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            self._log_request_failed("timeout")
            raise WttrTimeoutError("wttr.in request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            self._log_request_failed("http_status", status_code=exc.response.status_code)
            raise WttrClientError("wttr.in returned an unsuccessful status.") from exc
        except httpx.HTTPError as exc:
            self._log_request_failed("http_error")
            raise WttrClientError("wttr.in request failed.") from exc
        weather_response = self._extract_response(self._read_json(response), location)
        log_event(
            logger,
            logging.INFO,
            log_events.WTTR_RESPONSE_RECEIVED,
            status_code=response.status_code,
            forecast_day_count=len(weather_response.forecast),
        )
        return weather_response

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    def _read_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise WttrClientError("wttr.in returned an invalid JSON payload.") from exc

    def _extract_response(
        self,
        data: Any,
        requested_location: str,
    ) -> WeatherResponse:
        if not isinstance(data, dict):
            raise WttrClientError("wttr.in returned an invalid response payload.")
        current_condition = self._read_first_item(data, "current_condition")
        nearest_area = self._read_first_item(data, "nearest_area")
        return WeatherResponse(
            requested_location=requested_location,
            resolved_location=self._read_named_value(nearest_area, "areaName"),
            region=self._read_named_value(nearest_area, "region"),
            country=self._read_named_value(nearest_area, "country"),
            observation_time=self._read_required_text(current_condition, "localObsDateTime"),
            condition=self._read_named_value(current_condition, "weatherDesc"),
            temp_c=self._read_required_text(current_condition, "temp_C"),
            temp_f=self._read_required_text(current_condition, "temp_F"),
            feels_like_c=self._read_required_text(current_condition, "FeelsLikeC"),
            feels_like_f=self._read_required_text(current_condition, "FeelsLikeF"),
            humidity=self._read_required_text(current_condition, "humidity"),
            wind_speed_kmph=self._read_required_text(current_condition, "windspeedKmph"),
            wind_speed_miles=self._read_required_text(
                current_condition,
                "windspeedMiles",
            ),
            wind_direction=self._read_required_text(current_condition, "winddir16Point"),
            visibility_km=self._read_required_text(current_condition, "visibility"),
            forecast=self._read_forecast_days(data),
        )

    def _read_forecast_days(self, data: dict[str, Any]) -> list[WeatherForecastDay]:
        weather_items = data.get("weather")
        if not isinstance(weather_items, list) or not weather_items:
            raise WttrClientError("wttr.in returned an invalid weather forecast payload.")
        return [self._read_forecast_day(item) for item in weather_items]

    def _read_forecast_day(self, item: Any) -> WeatherForecastDay:
        if not isinstance(item, dict):
            raise WttrClientError("wttr.in returned an invalid forecast day payload.")
        astronomy = self._read_first_nested_item(item, "astronomy")
        representative_hour = self._select_representative_hour(item)
        return WeatherForecastDay(
            date=self._read_required_text(item, "date"),
            condition=self._read_named_value(representative_hour, "weatherDesc"),
            min_temp_c=self._read_required_text(item, "mintempC"),
            max_temp_c=self._read_required_text(item, "maxtempC"),
            min_temp_f=self._read_required_text(item, "mintempF"),
            max_temp_f=self._read_required_text(item, "maxtempF"),
            sunrise=self._read_required_text(astronomy, "sunrise"),
            sunset=self._read_required_text(astronomy, "sunset"),
        )

    def _select_representative_hour(self, item: dict[str, Any]) -> dict[str, Any]:
        hourly_items = item.get("hourly")
        if not isinstance(hourly_items, list) or not hourly_items:
            raise WttrClientError("wttr.in returned an invalid hourly forecast payload.")
        for hourly_item in hourly_items:
            if isinstance(hourly_item, dict) and hourly_item.get("time") == "1200":
                return hourly_item
        first_hour = hourly_items[0]
        if isinstance(first_hour, dict):
            return first_hour
        raise WttrClientError("wttr.in returned an invalid hourly forecast payload.")

    def _read_first_item(self, data: dict[str, Any], field_name: str) -> dict[str, Any]:
        items = data.get(field_name)
        if not isinstance(items, list) or not items:
            raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")
        first_item = items[0]
        if isinstance(first_item, dict):
            return first_item
        raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")

    def _read_first_nested_item(
        self,
        data: dict[str, Any],
        field_name: str,
    ) -> dict[str, Any]:
        items = data.get(field_name)
        if not isinstance(items, list) or not items:
            raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")
        first_item = items[0]
        if isinstance(first_item, dict):
            return first_item
        raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")

    def _read_named_value(self, data: dict[str, Any], field_name: str) -> str:
        items = data.get(field_name)
        if not isinstance(items, list) or not items:
            raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")
        first_item = items[0]
        if not isinstance(first_item, dict):
            raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")
        value = first_item.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")

    def _read_required_text(self, data: dict[str, Any], field_name: str) -> str:
        value = data.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise WttrClientError(f"wttr.in returned an invalid {field_name} payload.")

    def _log_request_failed(self, reason: str, status_code: int | None = None) -> None:
        fields: dict[str, object] = {"reason": reason}
        if status_code is not None:
            fields["status_code"] = status_code
        log_event(
            logger,
            logging.ERROR,
            log_events.WTTR_REQUEST_FAILED,
            **fields,
            exc_info=True,
        )
