from __future__ import annotations

from talking_telegram_bot.clients.chat_history_client import ChatHistoryClient
from talking_telegram_bot.models.messages import ChatHistoryEntry, ChatHistoryLog, ChatSummary


class ConversationContextService:
    def __init__(self, chat_history_client: ChatHistoryClient) -> None:
        self._chat_history_client = chat_history_client

    async def read_history(self, user_id: int) -> ChatHistoryLog:
        return await self._chat_history_client.read_history(user_id)

    async def append_entry(self, user_id: int, entry: ChatHistoryEntry) -> None:
        await self._chat_history_client.append_entry(user_id, entry)

    async def save_summary(
        self,
        user_id: int,
        summary: ChatSummary,
        summarized_entry_count: int,
    ) -> None:
        await self._chat_history_client.save_summary(
            user_id,
            summary,
            summarized_entry_count,
        )

    async def clear_history(self, user_id: int) -> None:
        await self._chat_history_client.clear_history(user_id)

