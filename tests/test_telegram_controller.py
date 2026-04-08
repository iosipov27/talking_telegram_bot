from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from talking_telegram_bot.controllers.telegram_controller import (
    SAFE_ERROR_MESSAGE,
    TelegramMessageController,
)
from talking_telegram_bot.services.message_service import MessageProcessingError


class TelegramControllerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_handle_text_message_sends_service_reply(self) -> None:
        message = SimpleNamespace(text="hi", reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        service = AsyncMock()
        service.generate_reply.return_value = "hello"
        controller = TelegramMessageController(service)

        await controller.handle_text_message(update, None)

        message.reply_text.assert_awaited_once_with("hello")

    async def test_handle_text_message_sends_safe_error_message(self) -> None:
        message = SimpleNamespace(text="hi", reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        service = AsyncMock()
        service.generate_reply.side_effect = MessageProcessingError("down")
        controller = TelegramMessageController(service)

        await controller.handle_text_message(update, None)

        message.reply_text.assert_awaited_once_with(SAFE_ERROR_MESSAGE)
