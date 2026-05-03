from __future__ import annotations

import logging

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.constants.user_messages import (
    FILE_READ_ERROR_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
    UNSUPPORTED_FILE_MESSAGE,
)
from talking_telegram_bot.messages.commands import ProcessDocumentMessage
from talking_telegram_bot.messages.events import (
    ResponseGenerated,
    TextReplyRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.services.agent_request_orchestrator_service import (
    AgentRequestOrchestratorService,
)
from talking_telegram_bot.services.file_processing_service import (
    FileProcessingError,
    FileProcessingService,
    FileTooLargeError,
    UnsupportedFileTypeError,
)

logger = logging.getLogger(__name__)


class ProcessDocumentMessageHandler:
    def __init__(
        self,
        file_processing_service: FileProcessingService,
        agent_request_orchestrator_service: AgentRequestOrchestratorService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._file_processing_service = file_processing_service
        self._agent_request_orchestrator_service = agent_request_orchestrator_service
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
            self._log_document_rejected(envelope, "unsupported_file_type")
            await self._reply_directly(envelope, UNSUPPORTED_FILE_MESSAGE)
            return
        except FileTooLargeError:
            self._log_document_rejected(envelope, "file_too_large")
            await self._reply_directly(
                envelope,
                FILE_TOO_LARGE_MESSAGE.format(
                    max_file_size_mb=self._file_processing_service.max_file_size_megabytes,
                ),
            )
            return
        except FileProcessingError:
            self._log_document_rejected(envelope, "file_processing_failed")
            await self._reply_directly(envelope, FILE_READ_ERROR_MESSAGE)
            return
        log_event(
            logger,
            logging.INFO,
            log_events.DOCUMENT_PROMPT_BUILT,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            file_name=envelope.message.file_name or "(missing)",
            file_size=envelope.message.file_size or 0,
            prompt_length=len(prompt_text),
        )
        await self._agent_request_orchestrator_service.publish_message_received(
            envelope,
            prompt_text,
        )
        try:
            await self._agent_request_orchestrator_service.start_agent_response(
                envelope,
                envelope.message.message,
                prompt_text,
                "document",
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                log_events.DOCUMENT_MESSAGE_PROCESSING_ERROR,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                stage="agent_request",
                exc_info=True,
            )
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

    def _log_document_rejected(
        self,
        envelope: MessageEnvelope[ProcessDocumentMessage],
        reason: str,
    ) -> None:
        log_event(
            logger,
            logging.WARNING,
            log_events.DOCUMENT_REJECTED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            file_name=envelope.message.file_name or "(missing)",
            file_size=envelope.message.file_size or 0,
            reason=reason,
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
