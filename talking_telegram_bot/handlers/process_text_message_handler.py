from __future__ import annotations

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants.user_messages import SAFE_LLM_ERROR_MESSAGE
from talking_telegram_bot.messages.commands import ProcessTextMessage
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    StartTelegramResponseSession,
    TextReplyRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.services.message_input_service import (
    MessageInputError,
    MessageInputService,
)
from talking_telegram_bot.services.prompt_builder_service import PromptBuilderService


class ProcessTextMessageHandler:
    def __init__(
        self,
        message_input_service: MessageInputService,
        prompt_builder_service: PromptBuilderService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._message_input_service = message_input_service
        self._prompt_builder_service = prompt_builder_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[ProcessTextMessage]) -> None:
        try:
            user_prompt = self._message_input_service.normalize_text(
                envelope.message.raw_text,
            )
        except MessageInputError:
            await self._event_bus.publish_and_wait(
                TextReplyRequested(
                    message=envelope.message.message,
                    text=SAFE_LLM_ERROR_MESSAGE,
                ),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
            return
        await self._event_bus.publish_and_wait(
            StartTelegramResponseSession(message=envelope.message.message),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        try:
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
        except Exception:
            await self._event_bus.publish_and_wait(
                UserFacingErrorRaised(text=SAFE_LLM_ERROR_MESSAGE),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )

