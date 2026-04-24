from __future__ import annotations

import logging

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.messages.events import MessageReceived, ResponseGenerated
from talking_telegram_bot.models.messages import ChatHistoryEntry
from talking_telegram_bot.services.conversation_context_service import (
    ConversationContextService,
)
from talking_telegram_bot.services.conversation_summary_service import (
    ConversationSummaryError,
    ConversationSummaryService,
)

logger = logging.getLogger(__name__)


class HistoryEventSubscriber:
    def __init__(
        self,
        conversation_context_service: ConversationContextService,
        conversation_summary_service: ConversationSummaryService | None = None,
    ) -> None:
        self._conversation_context_service = conversation_context_service
        self._conversation_summary_service = conversation_summary_service
        self._pending_requests: dict[tuple[int, str], tuple[str, str]] = {}

    async def handle(
        self,
        envelope: MessageEnvelope[MessageReceived | ResponseGenerated],
    ) -> None:
        if envelope.user_id is None:
            return
        if isinstance(envelope.message, MessageReceived):
            self._pending_requests[self._build_key(envelope)] = (
                envelope.message.text,
                envelope.created_at,
            )
            return
        request_text, created_at = self._pending_requests.pop(
            self._build_key(envelope),
            ("", envelope.created_at),
        )
        await self._conversation_context_service.append_entry(
            envelope.user_id,
            ChatHistoryEntry(
                request=request_text,
                response=envelope.message.text,
                created_at=created_at,
            ),
        )
        if self._conversation_summary_service is None:
            return
        try:
            await self._conversation_summary_service.summarize_if_needed(
                envelope.user_id,
            )
        except ConversationSummaryError as exc:
            logger.warning("Conversation summary update failed: %s", exc)

    def _build_key(
        self,
        envelope: MessageEnvelope[MessageReceived | ResponseGenerated],
    ) -> tuple[int, str]:
        return (envelope.user_id or 0, envelope.correlation_id)
