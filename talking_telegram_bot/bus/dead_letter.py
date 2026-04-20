from __future__ import annotations

import asyncio
import json
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.constants.logging_settings import CHAT_HISTORY_DIR_PATH

DEFAULT_DEAD_LETTER_PATH = CHAT_HISTORY_DIR_PATH / "dead_letter.jsonl"


class DeadLetterWriter:
    def __init__(self, path: Path = DEFAULT_DEAD_LETTER_PATH) -> None:
        self._path = path

    async def write(
        self,
        envelope: MessageEnvelope[Any],
        error: Exception,
    ) -> None:
        payload = {
            "message_id": envelope.message_id,
            "correlation_id": envelope.correlation_id,
            "causation_id": envelope.causation_id,
            "chat_id": envelope.chat_id,
            "user_id": envelope.user_id,
            "created_at": envelope.created_at,
            "message_type": type(envelope.message).__name__,
            "message": self._make_json_safe(envelope.message),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        await asyncio.to_thread(self._write_payload, payload)

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
            file.write("\n")

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): self._make_json_safe(nested_value)
                for key, nested_value in value.items()
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self._make_json_safe(item) for item in value]
        if is_dataclass(value):
            return {
                field.name: self._make_json_safe(getattr(value, field.name))
                for field in fields(value)
            }
        return repr(value)

