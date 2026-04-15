from datetime import UTC, datetime

from talking_telegram_bot.clients.chat_history_client import (
    ChatHistoryClient,
    ChatHistoryClientError,
    MAX_CHAT_HISTORY_ENTRIES,
)
from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.models.messages import (
    ChatHistoryEntry,
    ConversationMessage,
    UserMessage,
)


class MessageProcessingError(RuntimeError):
    """Raised when a user message can not be processed safely."""


class MessageService:
    def __init__(
        self,
        ollama_client: OllamaClient,
        chat_history_client: ChatHistoryClient,
    ) -> None:
        self._ollama_client = ollama_client
        self._chat_history_client = chat_history_client

    async def generate_reply(self, raw_text: str, user_id: int) -> str:
        user_message = self._normalize_message(raw_text)
        history_entries = await self._load_history(user_id)
        llm_messages = self._build_llm_messages(history_entries, user_message)
        try:
            assistant_message = await self._ollama_client.generate_reply(llm_messages)
        except OllamaClientError as exc:
            raise MessageProcessingError("LLM is unavailable.") from exc
        reply_text = assistant_message.text.strip()
        if not reply_text:
            raise MessageProcessingError("LLM returned an empty response.")
        await self._save_history(user_id, user_message.text, reply_text)
        return reply_text

    def _normalize_message(self, raw_text: str) -> UserMessage:
        normalized_text = raw_text.strip()
        if normalized_text:
            return UserMessage(text=normalized_text)
        raise MessageProcessingError("Message text is empty.")

    async def _load_history(self, user_id: int) -> list[ChatHistoryEntry]:
        try:
            return await self._chat_history_client.read_entries(user_id)
        except ChatHistoryClientError as exc:
            raise MessageProcessingError("Chat history is unavailable.") from exc

    def _build_llm_messages(
        self,
        history_entries: list[ChatHistoryEntry],
        user_message: UserMessage,
    ) -> list[ConversationMessage]:
        messages = []
        active_entries = history_entries[-(MAX_CHAT_HISTORY_ENTRIES - 1) :]
        for entry in active_entries:
            messages.append(ConversationMessage(role="user", content=entry.request))
            messages.append(
                ConversationMessage(role="assistant", content=entry.response),
            )
        messages.append(ConversationMessage(role="user", content=user_message.text))
        return messages

    async def _save_history(
        self,
        user_id: int,
        request_text: str,
        response_text: str,
    ) -> None:
        entry = ChatHistoryEntry(
            request=request_text,
            response=response_text,
            created_at=datetime.now(UTC).isoformat(),
        )
        try:
            await self._chat_history_client.append_entry(user_id, entry)
        except ChatHistoryClientError as exc:
            raise MessageProcessingError("Chat history is unavailable.") from exc
