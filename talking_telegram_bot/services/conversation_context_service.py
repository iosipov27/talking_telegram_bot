from __future__ import annotations

from talking_telegram_bot.clients.chat_history_client import (
    ChatHistoryClient,
    ChatHistoryClientError,
)
from talking_telegram_bot.constants.summary_settings import SUMMARY_CONTEXT_PREFIX
from talking_telegram_bot.models.messages import (
    ChatHistoryEntry,
    ChatHistoryLog,
    ChatSummary,
    ConversationMessage,
)


class ConversationContextError(RuntimeError):
    """Raised when conversation context can not be accessed safely."""


class ConversationContextService:
    def __init__(self, chat_history_client: ChatHistoryClient) -> None:
        self._chat_history_client = chat_history_client

    async def read_history(self, user_id: int) -> ChatHistoryLog:
        try:
            return await self._chat_history_client.read_history(user_id)
        except ChatHistoryClientError as exc:
            raise ConversationContextError("Failed to read conversation context.") from exc

    async def append_entry(self, user_id: int, entry: ChatHistoryEntry) -> None:
        try:
            await self._chat_history_client.append_entry(user_id, entry)
        except ChatHistoryClientError as exc:
            raise ConversationContextError("Failed to write conversation context.") from exc

    async def save_summary(
        self,
        user_id: int,
        summary: ChatSummary,
        summarized_entry_count: int,
    ) -> None:
        try:
            await self._chat_history_client.save_summary(
                user_id,
                summary,
                summarized_entry_count,
            )
        except ChatHistoryClientError as exc:
            raise ConversationContextError("Failed to write conversation summary.") from exc

    async def clear_history(self, user_id: int) -> None:
        try:
            await self._chat_history_client.clear_history(user_id)
        except ChatHistoryClientError as exc:
            raise ConversationContextError("Failed to clear conversation context.") from exc

    async def build_context_messages(self, user_id: int) -> list[ConversationMessage]:
        history_log = await self.read_history(user_id)
        messages: list[ConversationMessage] = []
        if history_log.summary is not None and history_log.summary.text.strip():
            messages.append(
                ConversationMessage(
                    role="system",
                    content=SUMMARY_CONTEXT_PREFIX.format(
                        summary=history_log.summary.text.strip(),
                    ),
                ),
            )
        for entry in self.read_complete_entries(history_log.entries):
            messages.append(
                ConversationMessage(role="user", content=entry.request.strip()),
            )
            messages.append(
                ConversationMessage(
                    role="assistant",
                    content=entry.response.strip(),
                )
            )
        return messages

    def read_complete_entries(
        self,
        entries: list[ChatHistoryEntry],
    ) -> list[ChatHistoryEntry]:
        complete_entries, _ = self.read_summarizable_entries(entries)
        return complete_entries

    def read_summarizable_entries(
        self,
        entries: list[ChatHistoryEntry],
    ) -> tuple[list[ChatHistoryEntry], int]:
        complete_entries: list[ChatHistoryEntry] = []
        pending_request: tuple[str, str] | None = None
        consumed_entry_count = 0
        for index, entry in enumerate(entries, start=1):
            request_text = entry.request.strip()
            response_text = entry.response.strip()
            if request_text and response_text:
                complete_entries.append(entry)
                pending_request = None
                consumed_entry_count = index
                continue
            if request_text:
                pending_request = (request_text, entry.created_at)
                continue
            if response_text and pending_request is not None:
                pending_text, created_at = pending_request
                complete_entries.append(
                    ChatHistoryEntry(
                        request=pending_text,
                        response=response_text,
                        created_at=created_at,
                    ),
                )
                pending_request = None
                consumed_entry_count = index
        return complete_entries, consumed_entry_count
