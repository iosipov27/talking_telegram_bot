from __future__ import annotations

import logging
from typing import Any

from talking_telegram_bot.logging_utils import (
    DEFAULT_TRACE_ID,
    get_current_log_context_value,
    get_current_request_id,
    get_current_trace_id,
)

try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
except ImportError:  # pragma: no cover - exercised when optional dependency is absent.
    sentry_sdk = None
    LoggingIntegration = None


SENTRY_CONTEXT_NAME = "telegram_bot_request"
_is_configured = False


class SentryConfigurationError(RuntimeError):
    """Raised when Sentry is enabled but the SDK is unavailable."""


def configure_sentry(
    *,
    dsn: str | None,
    environment: str,
) -> bool:
    if not dsn:
        return False
    if sentry_sdk is None or LoggingIntegration is None:
        raise SentryConfigurationError(
            "SENTRY_DSN is set but sentry-sdk is not installed.",
        )
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        send_default_pii=False,
        before_send=_add_request_context,
    )
    global _is_configured
    _is_configured = True
    return True


def capture_exception(
    error: BaseException,
    *,
    trace_id: str,
    request_id: str | None = None,
    chat_id: int | None = None,
    user_id: int | None = None,
    envelope_id: str | None = None,
    causation_id: str | None = None,
) -> None:
    if not _is_configured or sentry_sdk is None:
        return
    with sentry_sdk.push_scope() as scope:
        _apply_scope_context(
            scope,
            trace_id=trace_id,
            request_id=request_id or trace_id,
            chat_id=chat_id,
            user_id=user_id,
            envelope_id=envelope_id,
            causation_id=causation_id,
        )
        sentry_sdk.capture_exception(error)


def _add_request_context(
    event: dict[str, Any],
    hint: dict[str, Any],
) -> dict[str, Any] | None:
    del hint
    _add_json_log_extra(event)
    context = _read_event_context(event)
    if context["trace_id"] == DEFAULT_TRACE_ID and context["request_id"] == DEFAULT_TRACE_ID:
        return event
    tags = event.setdefault("tags", {})
    tags["trace_id"] = context["trace_id"]
    tags["request_id"] = context["request_id"]
    event.setdefault("contexts", {})[SENTRY_CONTEXT_NAME] = {
        key: value for key, value in context.items() if value is not None
    }
    user_id = context.get("user_id")
    if user_id is not None:
        event["user"] = {"id": str(user_id)}
    return event


def _add_json_log_extra(event: dict[str, Any]) -> None:
    payload = _build_json_log_payload(event)
    if payload is None:
        return
    extra = event.get("extra")
    if not isinstance(extra, dict):
        extra = {}
        event["extra"] = extra
    extra["json_log"] = payload


def _build_json_log_payload(event: dict[str, Any]) -> dict[str, Any] | None:
    message = _read_log_message(event)
    logger_name = _read_text(event.get("logger"))
    extra = event.get("extra")
    if not isinstance(extra, dict):
        extra = {}
    if message is None and logger_name is None and not extra:
        return None
    context = _read_event_context(event)
    payload: dict[str, Any] = {
        "level": _read_text(event.get("level")) or "error",
        "message": message or "",
        "service": _read_text(extra.get("service_name")) or logger_name or "sentry",
        "trace_id": context["trace_id"],
        "request_id": context["request_id"],
    }
    timestamp = _read_text(event.get("timestamp"))
    if timestamp is not None:
        payload["timestamp"] = timestamp
    for key in ("chat_id", "user_id", "envelope_id", "causation_id"):
        value = context.get(key)
        if value is not None:
            payload[key] = _to_json_safe(value)
    structured_fields = extra.get("structured_fields")
    if isinstance(structured_fields, dict):
        for key, value in structured_fields.items():
            if key not in {
                "timestamp",
                "level",
                "message",
                "service",
                "trace_id",
                "request_id",
            }:
                payload[key] = _to_json_safe(value)
    return payload


def _read_log_message(event: dict[str, Any]) -> str | None:
    logentry = event.get("logentry")
    if not isinstance(logentry, dict):
        return _read_text(event.get("message"))
    formatted = _read_text(logentry.get("formatted"))
    if formatted is not None:
        return formatted
    return _read_text(logentry.get("message"))


def _read_event_context(event: dict[str, Any]) -> dict[str, Any]:
    extra = event.get("extra")
    if not isinstance(extra, dict):
        extra = {}
    trace_id = (
        _read_text(extra.get("trace_id"))
        or get_current_trace_id()
        or DEFAULT_TRACE_ID
    )
    request_id = (
        _read_text(extra.get("request_id"))
        or get_current_request_id()
        or trace_id
    )
    return {
        "trace_id": trace_id,
        "request_id": request_id,
        "chat_id": extra.get("chat_id") or get_current_log_context_value("chat_id"),
        "user_id": extra.get("user_id") or get_current_log_context_value("user_id"),
        "envelope_id": _read_text(extra.get("envelope_id"))
        or _read_text(get_current_log_context_value("envelope_id")),
        "causation_id": _read_text(extra.get("causation_id"))
        or _read_text(get_current_log_context_value("causation_id")),
    }


def _apply_scope_context(
    scope,
    *,
    trace_id: str,
    request_id: str,
    chat_id: int | None,
    user_id: int | None,
    envelope_id: str | None,
    causation_id: str | None,
) -> None:
    scope.set_tag("trace_id", trace_id)
    scope.set_tag("request_id", request_id)
    scope.set_context(
        SENTRY_CONTEXT_NAME,
        {
            "trace_id": trace_id,
            "request_id": request_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "envelope_id": envelope_id,
            "causation_id": causation_id,
        },
    )
    if user_id is not None:
        scope.set_user({"id": str(user_id)})


def _read_text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {
            str(key): _to_json_safe(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    return str(value)
