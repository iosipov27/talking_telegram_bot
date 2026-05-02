from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.controllers.telegram_text_controller import (
    TelegramTextController,
)
from talking_telegram_bot.logging_utils import JsonLogFormatter


class TelegramTextControllerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_inbound_text_log_has_trace_id_without_message_content(self) -> None:
        message = SimpleNamespace(text="hello secret", reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=10),
            effective_user=SimpleNamespace(id=20),
        )
        command_bus = AsyncMock()
        controller = TelegramTextController(command_bus, AsyncMock())

        with self.assertLogs(
            "talking_telegram_bot.controllers.telegram_text_controller",
            level="INFO",
        ) as logs:
            await controller.handle_text_message(update, None)

        payload = json.loads(JsonLogFormatter().format(logs.records[0]))
        self.assertEqual(payload["message"], log_events.TEXT_MESSAGE_RECEIVED)
        self.assertEqual(payload["chat_id"], 10)
        self.assertEqual(payload["user_id"], 20)
        self.assertEqual(payload["text_length"], 12)
        self.assertNotEqual(payload["trace_id"], "system")
        self.assertNotIn("hello secret", json.dumps(payload))

