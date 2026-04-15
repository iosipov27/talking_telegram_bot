from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.clients.chat_history_client import (
    ChatHistoryClientError,
    MAX_CHAT_HISTORY_ENTRIES,
)
from talking_telegram_bot.clients.ollama_client import OllamaClientError
from talking_telegram_bot.models.messages import AssistantMessage, ChatHistoryEntry
from talking_telegram_bot.services.message_service import (
    MessageProcessingError,
    MessageService,
)


class MessageServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_generate_reply_returns_trimmed_text(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="  hello  ")
        history_client = AsyncMock()
        history_client.read_entries.return_value = []
        service = MessageService(ollama_client, history_client)

        reply_text = await service.generate_reply("  hi  ", 123)

        self.assertEqual(reply_text, "hello")
        ollama_client.generate_reply.assert_awaited_once()

    async def test_generate_reply_saves_chat_history(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="  hello  ")
        history_client = AsyncMock()
        history_client.read_entries.return_value = []
        service = MessageService(ollama_client, history_client)

        await service.generate_reply("  hi  ", 123)

        history_client.append_entry.assert_awaited_once()
        user_id, entry = history_client.append_entry.await_args.args
        self.assertEqual(user_id, 123)
        self.assertEqual(entry.request, "hi")
        self.assertEqual(entry.response, "hello")
        self.assertTrue(entry.created_at)

    async def test_generate_reply_sends_history_and_new_message_to_llm(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="new answer")
        history_client = AsyncMock()
        history_client.read_entries.return_value = [
            ChatHistoryEntry(
                request="old question",
                response="old answer",
                created_at="2026-04-15T10:00:00+00:00",
            ),
        ]
        service = MessageService(ollama_client, history_client)

        await service.generate_reply("new question", 123)

        llm_messages = ollama_client.generate_reply.await_args.args[0]
        self.assertEqual(
            [(message.role, message.content) for message in llm_messages],
            [
                ("user", "old question"),
                ("assistant", "old answer"),
                ("user", "new question"),
            ],
        )

    async def test_generate_reply_sends_only_active_messages_to_llm(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="new answer")
        history_client = AsyncMock()
        history_client.read_entries.return_value = [
            ChatHistoryEntry(
                request=f"question-{index}",
                response=f"answer-{index}",
                created_at=f"2026-04-15T10:{index:02d}:00+00:00",
            )
            for index in range(MAX_CHAT_HISTORY_ENTRIES)
        ]
        service = MessageService(ollama_client, history_client)

        await service.generate_reply("new question", 123)

        llm_messages = ollama_client.generate_reply.await_args.args[0]
        user_contents = [
            message.content for message in llm_messages if message.role == "user"
        ]
        self.assertEqual(len(user_contents), MAX_CHAT_HISTORY_ENTRIES)
        self.assertEqual(user_contents[0], "question-1")
        self.assertEqual(user_contents[-1], "new question")

    async def test_generate_reply_raises_for_empty_response(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="   ")
        history_client = AsyncMock()
        history_client.read_entries.return_value = []
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    async def test_generate_reply_maps_client_errors(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = OllamaClientError("down")
        history_client = AsyncMock()
        history_client.read_entries.return_value = []
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    async def test_generate_reply_maps_history_errors(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="hello")
        history_client = AsyncMock()
        history_client.read_entries.return_value = []
        history_client.append_entry.side_effect = ChatHistoryClientError("down")
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    async def test_generate_reply_maps_history_read_errors(self) -> None:
        ollama_client = AsyncMock()
        history_client = AsyncMock()
        history_client.read_entries.side_effect = ChatHistoryClientError("down")
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

        ollama_client.generate_reply.assert_not_awaited()
