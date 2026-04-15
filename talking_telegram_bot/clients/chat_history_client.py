from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from talking_telegram_bot.constants.logging_settings import CHAT_HISTORY_DIR_PATH
from talking_telegram_bot.models.messages import ChatHistoryEntry


class ChatHistoryClientError(RuntimeError):
    """Raised when chat history can not be accessed safely."""


class ChatHistoryClient:
    def __init__(self, history_dir: Path = CHAT_HISTORY_DIR_PATH) -> None:
        self._history_dir = history_dir
        self._locks: dict[int, asyncio.Lock] = {}

    async def append_entry(
        self,
        user_id: int,
        entry: ChatHistoryEntry,
    ) -> None:
        async with self._get_lock(user_id):
            try:
                await asyncio.to_thread(self._append_entry_sync, user_id, entry)
            except (OSError, TypeError, ValueError) as exc:
                raise ChatHistoryClientError("Failed to write chat history.") from exc

    async def read_entries(self, user_id: int) -> list[ChatHistoryEntry]:
        async with self._get_lock(user_id):
            try:
                return await asyncio.to_thread(self._read_entries_sync, user_id)
            except (OSError, TypeError, ValueError) as exc:
                raise ChatHistoryClientError("Failed to read chat history.") from exc

    def _get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _append_entry_sync(self, user_id: int, entry: ChatHistoryEntry) -> None:
        self._history_dir.mkdir(parents=True, exist_ok=True)
        history_file_path = self._build_history_file_path(user_id)
        history_payload = self._read_history_payload(history_file_path, user_id)
        self._read_history_entries(history_payload)
        history_payload["history"].append(asdict(entry))
        self._write_history_payload(history_file_path, history_payload)

    def _read_entries_sync(self, user_id: int) -> list[ChatHistoryEntry]:
        history_file_path = self._build_history_file_path(user_id)
        history_payload = self._read_history_payload(history_file_path, user_id)
        return self._read_history_entries(history_payload)

    def _build_history_file_path(self, user_id: int) -> Path:
        return self._history_dir / f"chat_history_{user_id}.json"

    def _read_history_payload(self, path: Path, user_id: int) -> dict[str, Any]:
        if not path.exists():
            return {"user_id": user_id, "history": []}
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if self._is_valid_history_payload(payload, user_id):
            return payload
        raise ChatHistoryClientError("Chat history file has an invalid format.")

    def _is_valid_history_payload(self, payload: Any, user_id: int) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("user_id") != user_id:
            return False
        return isinstance(payload.get("history"), list)

    def _read_history_entries(
        self,
        payload: dict[str, Any],
    ) -> list[ChatHistoryEntry]:
        entries = []
        for item in payload["history"]:
            if not self._is_valid_history_entry(item):
                raise ChatHistoryClientError(
                    "Chat history entry has an invalid format.",
                )
            entries.append(
                ChatHistoryEntry(
                    request=item["request"],
                    response=item["response"],
                    created_at=item["created_at"],
                ),
            )
        return entries

    def _is_valid_history_entry(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        return all(
            isinstance(item.get(field_name), str)
            for field_name in ("request", "response", "created_at")
        )

    def _write_history_payload(self, path: Path, payload: dict[str, Any]) -> None:
        temporary_path = path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_path.replace(path)
