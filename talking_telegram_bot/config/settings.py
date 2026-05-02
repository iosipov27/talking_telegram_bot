from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from talking_telegram_bot.constants.prompt_settings import DEFAULT_AGENT_ROLE


class SettingsError(RuntimeError):
    """Raised when environment settings are missing or invalid."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_model: str
    ollama_agent_role: str
    ollama_timeout_seconds: float
    tavily_api_key: str
    tavily_base_url: str
    tavily_timeout_seconds: float
    nominatim_base_url: str
    nominatim_timeout_seconds: float
    nominatim_user_agent: str
    wttr_base_url: str
    wttr_timeout_seconds: float
    telegram_concurrent_updates: int
    conversation_history_enabled: bool
    sentry_dsn: str | None
    sentry_environment: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        telegram_bot_token=_read_required_env("TELEGRAM_BOT_TOKEN"),
        ollama_base_url=_read_required_env("OLLAMA_BASE_URL"),
        ollama_model=_read_required_env("OLLAMA_MODEL"),
        ollama_agent_role=_read_text_env("OLLAMA_AGENT_ROLE", DEFAULT_AGENT_ROLE),
        ollama_timeout_seconds=_read_positive_float_env("OLLAMA_TIMEOUT_SECONDS"),
        tavily_api_key=_read_required_env("TAVILY_API_KEY"),
        tavily_base_url=_read_text_env("TAVILY_BASE_URL", "https://api.tavily.com"),
        tavily_timeout_seconds=_read_positive_float_env_with_default(
            "TAVILY_TIMEOUT_SECONDS",
            default=15.0,
        ),
        nominatim_base_url=_read_text_env(
            "NOMINATIM_BASE_URL",
            "https://nominatim.openstreetmap.org",
        ),
        nominatim_timeout_seconds=_read_positive_float_env_with_default(
            "NOMINATIM_TIMEOUT_SECONDS",
            default=10.0,
        ),
        nominatim_user_agent=_read_text_env(
            "NOMINATIM_USER_AGENT",
            "talking_telegram_bot/1.0",
        ),
        wttr_base_url=_read_text_env("WTTR_BASE_URL", "https://wttr.in"),
        wttr_timeout_seconds=_read_positive_float_env_with_default(
            "WTTR_TIMEOUT_SECONDS",
            default=10.0,
        ),
        telegram_concurrent_updates=_read_positive_int_env(
            "TELEGRAM_CONCURRENT_UPDATES",
            default=8,
        ),
        conversation_history_enabled=_read_bool_env(
            "CONVERSATION_HISTORY_ENABLED",
            default=False,
        ),
        sentry_dsn=_read_optional_text_env("SENTRY_DSN"),
        sentry_environment=_read_text_env("SENTRY_ENVIRONMENT", "development"),
    )


def _read_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    raise SettingsError(f"Environment variable {name} is required.")


def _read_text_env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    return default


def _read_optional_text_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if value:
        return value
    return None


def _read_positive_float_env(name: str) -> float:
    value = _read_required_env(name)
    return _parse_positive_float(name, value)


def _read_positive_float_env_with_default(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return _parse_positive_float(name, value)


def _parse_positive_float(name: str, raw_value: str) -> float:
    try:
        number = float(raw_value)
    except ValueError as exc:
        raise SettingsError(f"Environment variable {name} must be a number.") from exc
    if number > 0:
        return number
    raise SettingsError(f"Environment variable {name} must be greater than 0.")


def _read_positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise SettingsError(f"Environment variable {name} must be an integer.") from exc
    if number > 0:
        return number
    raise SettingsError(f"Environment variable {name} must be greater than 0.")


def _read_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized_value = value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise SettingsError(
        f"Environment variable {name} must be true or false.",
    )
