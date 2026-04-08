from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class SettingsError(RuntimeError):
    """Raised when environment settings are missing or invalid."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    telegram_concurrent_updates: int


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        telegram_bot_token=_read_required_env("TELEGRAM_BOT_TOKEN"),
        ollama_base_url=_read_required_env("OLLAMA_BASE_URL"),
        ollama_model=_read_required_env("OLLAMA_MODEL"),
        ollama_timeout_seconds=_read_positive_float_env("OLLAMA_TIMEOUT_SECONDS"),
        telegram_concurrent_updates=_read_positive_int_env(
            "TELEGRAM_CONCURRENT_UPDATES",
            default=8,
        ),
    )


def _read_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    raise SettingsError(f"Environment variable {name} is required.")


def _read_positive_float_env(name: str) -> float:
    value = _read_required_env(name)
    try:
        number = float(value)
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
