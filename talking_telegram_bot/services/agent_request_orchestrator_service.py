from __future__ import annotations

import logging
from typing import Any

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    MessageReceived,
    StartTelegramResponseSession,
)
from talking_telegram_bot.services.prompt_builder_service import PromptBuilderService

logger = logging.getLogger(__name__)


class AgentRequestOrchestratorService:
    def __init__(
        self,
        prompt_builder_service: PromptBuilderService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._prompt_builder_service = prompt_builder_service
        self._event_bus = event_bus

    async def publish_message_received(
        self,
        envelope: MessageEnvelope[Any],
        text: str,
    ) -> None:
        await self._event_bus.publish_and_wait(
            MessageReceived(text=text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )

    async def start_agent_response(
        self,
        envelope: MessageEnvelope[Any],
        telegram_message: Any,
        user_prompt: str,
        source: str,
    ) -> None:
        await self._event_bus.publish_and_wait(
            StartTelegramResponseSession(message=telegram_message),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_RUN_REQUESTED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            source=source,
        )
        await self._event_bus.publish_and_wait(
            AgentRunRequested(
                system_prompt=self._prompt_builder_service.build_system_prompt(),
                user_prompt=user_prompt,
            ),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
