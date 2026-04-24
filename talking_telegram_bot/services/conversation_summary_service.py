from __future__ import annotations

from datetime import datetime

from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.constants.summary_settings import (
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_TRIGGER_ENTRIES,
    SUMMARY_UPDATE_PROMPT,
)
from talking_telegram_bot.models.messages import (
    ChatSummary,
    ConversationMessage,
)
from talking_telegram_bot.services.conversation_context_service import (
    ConversationContextError,
    ConversationContextService,
)


class ConversationSummaryError(RuntimeError):
    """Raised when conversation summary can not be updated safely."""


class ConversationSummaryService:
    def __init__(
        self,
        conversation_context_service: ConversationContextService,
        ollama_client: OllamaClient,
    ) -> None:
        self._conversation_context_service = conversation_context_service
        self._ollama_client = ollama_client

    async def summarize_if_needed(self, user_id: int) -> None:
        try:
            history_log = await self._conversation_context_service.read_history(user_id)
        except ConversationContextError as exc:
            raise ConversationSummaryError("Failed to read conversation history.") from exc
        entries, consumed_entry_count = (
            self._conversation_context_service.read_summarizable_entries(
                history_log.entries,
            )
        )
        if len(entries) < SUMMARY_TRIGGER_ENTRIES:
            return
        messages = self._build_summary_messages(entries, history_log.summary)
        try:
            assistant_message = await self._ollama_client.generate_reply(messages)
        except OllamaClientError as exc:
            raise ConversationSummaryError("Failed to generate conversation summary.") from exc
        summary_text = assistant_message.text.strip()
        if not summary_text:
            raise ConversationSummaryError("Generated conversation summary is empty.")
        try:
            await self._conversation_context_service.save_summary(
                user_id,
                ChatSummary(
                    text=summary_text,
                    updated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
                consumed_entry_count,
            )
        except ConversationContextError as exc:
            raise ConversationSummaryError("Failed to save conversation summary.") from exc

    def _build_summary_messages(
        self,
        entries: list[ChatHistoryEntry],
        existing_summary: ChatSummary | None,
    ) -> list[ConversationMessage]:
        messages = [ConversationMessage(role="system", content=SUMMARY_SYSTEM_PROMPT)]
        if existing_summary is not None and existing_summary.text.strip():
            messages.append(
                ConversationMessage(
                    role="user",
                    content=(
                        "Existing conversation summary:\n"
                        f"{existing_summary.text.strip()}"
                    ),
                ),
            )
        for entry in entries:
            messages.append(
                ConversationMessage(role="user", content=entry.request.strip()),
            )
            messages.append(
                ConversationMessage(role="assistant", content=entry.response.strip()),
            )
        messages.append(ConversationMessage(role="user", content=SUMMARY_UPDATE_PROMPT))
        return messages
