from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.constants.user_messages import LLM_THINKING_MESSAGE
from talking_telegram_bot.controllers.telegram_outbound_controller import (
    TelegramOutboundController,
)
from talking_telegram_bot.messages.events import (
    ProgressUpdated,
    ReplyReady,
    StartTelegramResponseSession,
    UserFacingErrorRaised,
)


class TelegramOutboundControllerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_reply_session_updates_progress_and_sends_final_reply(self) -> None:
        progress_message = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
        message = SimpleNamespace(
            reply_text=AsyncMock(side_effect=[progress_message, None]),
        )
        controller = TelegramOutboundController()

        await controller.handle(
            MessageEnvelope(
                message=StartTelegramResponseSession(message=message),
                correlation_id="corr-4",
            ),
        )
        await controller.handle(
            MessageEnvelope(
                message=ProgressUpdated(text="Working..."),
                correlation_id="corr-4",
            ),
        )
        await controller.handle(
            MessageEnvelope(
                message=ReplyReady(text="done"),
                correlation_id="corr-4",
            ),
        )

        message.reply_text.assert_has_awaits(
            [
                call(LLM_THINKING_MESSAGE),
                call("done"),
            ],
        )
        progress_message.edit_text.assert_awaited_once_with("Working...")
        progress_message.delete.assert_awaited_once()

    async def test_user_facing_error_uses_fallback_message_when_no_session(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        controller = TelegramOutboundController()

        await controller.handle(
            MessageEnvelope(
                message=UserFacingErrorRaised(
                    text="safe error",
                    fallback_message=message,
                ),
                correlation_id="missing-session",
            ),
        )

        message.reply_text.assert_awaited_once_with("safe error")

