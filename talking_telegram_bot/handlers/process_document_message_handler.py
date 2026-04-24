from __future__ import annotations

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants.user_messages import (
    FILE_READ_ERROR_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
    UNSUPPORTED_FILE_MESSAGE,
)
from talking_telegram_bot.messages.commands import ProcessDocumentMessage
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    MessageReceived,
    ResponseGenerated,
    StartTelegramResponseSession,
    TextReplyRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.services.file_processing_service import (
    FileProcessingError,
    FileProcessingService,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from talking_telegram_bot.services.prompt_builder_service import PromptBuilderService


class ProcessDocumentMessageHandler:
    def __init__(
        self,
        file_processing_service: FileProcessingService,
        prompt_builder_service: PromptBuilderService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._file_processing_service = file_processing_service
        self._prompt_builder_service = prompt_builder_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[ProcessDocumentMessage]) -> None:
        try:
            self._file_processing_service.validate_metadata(
                envelope.message.file_name,
                envelope.message.file_size,
            )
            prompt_text = self._file_processing_service.build_llm_prompt(
                envelope.message.file_name,
                envelope.message.content,
            )
        except UnsupportedFileTypeError:
            await self._reply_directly(envelope, UNSUPPORTED_FILE_MESSAGE)
            return
        except FileTooLargeError:
            await self._reply_directly(
                envelope,
                FILE_TOO_LARGE_MESSAGE.format(
                    max_file_size_mb=self._file_processing_service.max_file_size_megabytes,
                ),
            )
            return
        except FileProcessingError:
            await self._reply_directly(envelope, FILE_READ_ERROR_MESSAGE)
            return
        await self._event_bus.publish_and_wait(
            MessageReceived(text=prompt_text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
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
                    user_prompt=prompt_text,
                ),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
        except Exception:
            await self._event_bus.publish_and_wait(
                ResponseGenerated(text=SAFE_LLM_ERROR_MESSAGE),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
            await self._event_bus.publish_and_wait(
                UserFacingErrorRaised(text=SAFE_LLM_ERROR_MESSAGE),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )

    async def _reply_directly(
        self,
        envelope: MessageEnvelope[ProcessDocumentMessage],
        text: str,
    ) -> None:
        await self._event_bus.publish_and_wait(
            ResponseGenerated(text=text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        await self._event_bus.publish_and_wait(
            TextReplyRequested(
                message=envelope.message.message,
                text=text,
            ),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
