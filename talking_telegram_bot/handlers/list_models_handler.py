from __future__ import annotations

import logging

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.user_messages import SAFE_MODEL_ERROR_MESSAGE
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.commands import ListModels
from talking_telegram_bot.messages.events import ModelListReady, TextReplyRequested
from talking_telegram_bot.services.model_runtime_service import (
    ModelRuntimeError,
    ModelRuntimeService,
)

logger = logging.getLogger(__name__)


class ListModelsHandler:
    def __init__(
        self,
        model_runtime_service: ModelRuntimeService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._model_runtime_service = model_runtime_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[ListModels]) -> None:
        try:
            available_models = await self._model_runtime_service.list_models()
        except ModelRuntimeError:
            log_event(
                logger,
                logging.ERROR,
                log_events.MODEL_LIST_ERROR,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                exc_info=True,
            )
            await self._event_bus.publish_and_wait(
                TextReplyRequested(
                    message=envelope.message.message,
                    text=SAFE_MODEL_ERROR_MESSAGE,
                ),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
            return
        log_event(
            logger,
            logging.INFO,
            log_events.MODEL_LIST_SENT,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            current_model=available_models.current_model,
            model_count=len(available_models.model_names),
        )
        await self._event_bus.publish_and_wait(
            ModelListReady(
                message=envelope.message.message,
                current_model=available_models.current_model,
                model_names=available_models.model_names,
            ),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
