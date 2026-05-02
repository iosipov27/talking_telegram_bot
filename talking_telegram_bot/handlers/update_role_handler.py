from __future__ import annotations

import logging

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.user_messages import ROLE_MESSAGE, ROLE_UPDATED_MESSAGE
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.commands import UpdateRole
from talking_telegram_bot.messages.events import TextReplyRequested
from talking_telegram_bot.services.role_runtime_service import (
    RoleRuntimeError,
    RoleRuntimeService,
)

logger = logging.getLogger(__name__)


class UpdateRoleHandler:
    def __init__(
        self,
        role_runtime_service: RoleRuntimeService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._role_runtime_service = role_runtime_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[UpdateRole]) -> None:
        try:
            selected_role = self._role_runtime_service.set_agent_role(
                envelope.message.raw_role,
            )
        except RoleRuntimeError:
            log_event(
                logger,
                logging.WARNING,
                log_events.ROLE_UPDATE_ERROR,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                requested_role_length=len(envelope.message.raw_role),
                exc_info=True,
            )
            reply_text = ROLE_MESSAGE.format(
                agent_role=self._role_runtime_service.get_current_agent_role(),
            )
        else:
            log_event(
                logger,
                logging.INFO,
                log_events.ROLE_UPDATED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                role_length=len(selected_role),
            )
            reply_text = ROLE_UPDATED_MESSAGE.format(agent_role=selected_role)
        await self._event_bus.publish_and_wait(
            TextReplyRequested(
                message=envelope.message.message,
                text=reply_text,
            ),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
