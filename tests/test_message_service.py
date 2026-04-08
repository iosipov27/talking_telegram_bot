from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.clients.ollama_client import OllamaClientError
from talking_telegram_bot.models.messages import AssistantMessage
from talking_telegram_bot.services.message_service import (
    MessageProcessingError,
    MessageService,
)


class MessageServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_generate_reply_returns_trimmed_text(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="  hello  ")
        service = MessageService(ollama_client)

        reply_text = await service.generate_reply("  hi  ")

        self.assertEqual(reply_text, "hello")
        ollama_client.generate_reply.assert_awaited_once()

    async def test_generate_reply_raises_for_empty_response(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="   ")
        service = MessageService(ollama_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi")

    async def test_generate_reply_maps_client_errors(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = OllamaClientError("down")
        service = MessageService(ollama_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi")
