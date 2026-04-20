from __future__ import annotations

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants.user_messages import ROLE_MESSAGE
from talking_telegram_bot.messages.commands import ShowRole
from talking_telegram_bot.messages.events import TextReplyRequested
from talking_telegram_bot.services.role_runtime_service import RoleRuntimeService


class ShowRoleHandler:
    def __init__(
        self,
        role_runtime_service: RoleRuntimeService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._role_runtime_service = role_runtime_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[ShowRole]) -> None:
        await self._event_bus.publish_and_wait(
            TextReplyRequested(
                message=envelope.message.message,
                text=ROLE_MESSAGE.format(
                    agent_role=self._role_runtime_service.get_current_agent_role(),
                ),
            ),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )

