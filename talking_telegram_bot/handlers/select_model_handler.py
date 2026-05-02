from __future__ import annotations

import logging

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.telegram import MODEL_CALLBACK_PREFIX
from talking_telegram_bot.constants.user_messages import (
    MODEL_SELECTED_MESSAGE,
    SAFE_MODEL_ERROR_MESSAGE,
)
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.commands import SelectModel
from talking_telegram_bot.messages.events import CallbackTextRequested
from talking_telegram_bot.services.model_runtime_service import (
    ModelRuntimeError,
    ModelRuntimeService,
)

logger = logging.getLogger(__name__)


class SelectModelHandler:
    def __init__(
        self,
        model_runtime_service: ModelRuntimeService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._model_runtime_service = model_runtime_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[SelectModel]) -> None:
        try:
            raw_index = envelope.message.callback_data.removeprefix(MODEL_CALLBACK_PREFIX)
            model_index = int(raw_index)
            selected_model = await self._model_runtime_service.select_model_by_index(
                model_index,
            )
        except (ValueError, ModelRuntimeError):
            log_event(
                logger,
                logging.WARNING,
                log_events.MODEL_SELECTION_ERROR,
                trace_id=envelope.correlation_id,
                user_id=envelope.user_id,
                callback_data=envelope.message.callback_data,
                exc_info=True,
            )
            reply_text = SAFE_MODEL_ERROR_MESSAGE
        else:
            log_event(
                logger,
                logging.INFO,
                log_events.MODEL_SWITCHED,
                trace_id=envelope.correlation_id,
                user_id=envelope.user_id,
                selected_model=selected_model,
            )
            reply_text = MODEL_SELECTED_MESSAGE.format(selected_model=selected_model)
        await self._event_bus.publish_and_wait(
            CallbackTextRequested(
                callback_query=envelope.message.callback_query,
                text=reply_text,
            ),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
