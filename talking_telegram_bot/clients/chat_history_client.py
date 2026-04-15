from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from talking_telegram_bot.constants.logging_settings import CHAT_HISTORY_DIR_PATH
from talking_telegram_bot.models.messages import (
    ChatHistoryEntry,
    ChatHistoryLog,
    ChatSummary,
)

MAX_CHAT_HISTORY_ENTRIES = 10


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
        history_log = await self.read_history(user_id)
        return history_log.entries

    async def read_history(self, user_id: int) -> ChatHistoryLog:
        async with self._get_lock(user_id):
            try:
                return await asyncio.to_thread(self._read_history_sync, user_id)
            except (OSError, TypeError, ValueError) as exc:
                raise ChatHistoryClientError("Failed to read chat history.") from exc

    async def save_summary(
        self,
        user_id: int,
        summary: ChatSummary,
        summarized_entry_count: int,
    ) -> None:
        async with self._get_lock(user_id):
            try:
                await asyncio.to_thread(
                    self._save_summary_sync,
                    user_id,
                    summary,
                    summarized_entry_count,
                )
            except (OSError, TypeError, ValueError) as exc:
                raise ChatHistoryClientError("Failed to write chat summary.") from exc

    async def clear_history(self, user_id: int) -> None:
        async with self._get_lock(user_id):
            try:
                await asyncio.to_thread(self._clear_history_sync, user_id)
            except OSError as exc:
                raise ChatHistoryClientError("Failed to clear chat history.") from exc

    def _get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _append_entry_sync(self, user_id: int, entry: ChatHistoryEntry) -> None:
        self._history_dir.mkdir(parents=True, exist_ok=True)
        history_file_path = self._build_history_file_path(user_id)
        history_payload = self._read_history_payload(history_file_path, user_id)
        history_entries = self._read_history_entries(history_payload)
        history_entries.append(entry)
        history_payload["history"] = [
            asdict(history_entry)
            for history_entry in self._limit_history_entries(history_entries)
        ]
        self._write_history_payload(history_file_path, history_payload)

    def _read_history_sync(self, user_id: int) -> ChatHistoryLog:
        history_file_path = self._build_history_file_path(user_id)
        history_payload = self._read_history_payload(history_file_path, user_id)
        return ChatHistoryLog(
            summary=self._read_summary(history_payload),
            entries=self._limit_history_entries(
                self._read_history_entries(history_payload),
            ),
        )

    def _save_summary_sync(
        self,
        user_id: int,
        summary: ChatSummary,
        summarized_entry_count: int,
    ) -> None:
        self._history_dir.mkdir(parents=True, exist_ok=True)
        history_file_path = self._build_history_file_path(user_id)
        history_payload = self._read_history_payload(history_file_path, user_id)
        history_entries = self._limit_history_entries(
            self._read_history_entries(history_payload),
        )
        history_payload["summary"] = asdict(summary)
        history_payload["history"] = [
            asdict(history_entry)
            for history_entry in self._limit_history_entries(
                history_entries[summarized_entry_count:],
            )
        ]
        self._write_history_payload(history_file_path, history_payload)

    def _build_history_file_path(self, user_id: int) -> Path:
        return self._history_dir / f"chat_history_{user_id}.json"

    def _clear_history_sync(self, user_id: int) -> None:
        history_file_path = self._build_history_file_path(user_id)
        if history_file_path.exists():
            history_file_path.unlink()

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
        if not isinstance(payload.get("history"), list):
            return False
        return self._is_valid_summary(payload.get("summary"))

    def _read_summary(self, payload: dict[str, Any]) -> ChatSummary | None:
        summary = payload.get("summary")
        if summary is None:
            return None
        if not self._is_valid_summary(summary):
            raise ChatHistoryClientError("Chat summary has an invalid format.")
        return ChatSummary(
            text=summary["text"],
            updated_at=summary["updated_at"],
        )

    def _is_valid_summary(self, summary: Any) -> bool:
        if summary is None:
            return True
        if not isinstance(summary, dict):
            return False
        return all(
            isinstance(summary.get(field_name), str)
            for field_name in ("text", "updated_at")
        )

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

    def _limit_history_entries(
        self,
        entries: list[ChatHistoryEntry],
    ) -> list[ChatHistoryEntry]:
        return entries[-MAX_CHAT_HISTORY_ENTRIES:]

    def _write_history_payload(self, path: Path, payload: dict[str, Any]) -> None:
        temporary_path = path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_path.replace(path)
