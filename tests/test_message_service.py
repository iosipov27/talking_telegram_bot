from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.clients.chat_history_client import (
    ChatHistoryClientError,
)
from talking_telegram_bot.clients.ollama_client import OllamaClientError
from talking_telegram_bot.constants.prompt_settings import AGENT_SYSTEM_PROMPT
from talking_telegram_bot.constants.summary_settings import SUMMARY_TRIGGER_ENTRIES
from talking_telegram_bot.models.messages import (
    AssistantMessage,
    ChatHistoryEntry,
    ChatHistoryLog,
    ChatSummary,
)
from talking_telegram_bot.services.message_service import (
    AgentRoleSelectionError,
    MessageProcessingError,
    MessageService,
)


class MessageServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_generate_reply_returns_trimmed_text(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="  hello  ")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[],
        )
        service = MessageService(ollama_client, history_client)

        reply_text = await service.generate_reply("  hi  ", 123)

        self.assertEqual(reply_text, "hello")
        ollama_client.generate_reply.assert_awaited_once()

    async def test_generate_reply_saves_chat_history(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="  hello  ")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[],
        )
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
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[
                ChatHistoryEntry(
                    request="old question",
                    response="old answer",
                    created_at="2026-04-15T10:00:00+00:00",
                ),
            ],
        )
        service = MessageService(ollama_client, history_client)

        await service.generate_reply("new question", 123)

        llm_messages = ollama_client.generate_reply.await_args.args[0]
        self.assertEqual(
            [(message.role, message.content) for message in llm_messages],
            [
                (
                    "system",
                    AGENT_SYSTEM_PROMPT.format(
                        agent_role="опытный программист",
                    ),
                ),
                ("user", "old question"),
                ("assistant", "old answer"),
                ("user", "new question"),
            ],
        )

    async def test_generate_reply_sends_unsummarized_history_to_llm(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="new answer")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[
                ChatHistoryEntry(
                    request=f"question-{index}",
                    response=f"answer-{index}",
                    created_at=f"2026-04-15T10:{index:02d}:00+00:00",
                )
                for index in range(SUMMARY_TRIGGER_ENTRIES - 1)
            ],
        )
        service = MessageService(ollama_client, history_client)

        await service.generate_reply("new question", 123)

        llm_messages = ollama_client.generate_reply.await_args.args[0]
        user_contents = [
            message.content for message in llm_messages if message.role == "user"
        ]
        self.assertEqual(len(user_contents), SUMMARY_TRIGGER_ENTRIES)
        self.assertEqual(user_contents[0], "question-0")
        self.assertEqual(user_contents[-1], "new question")

    async def test_generate_reply_sends_summary_and_new_message_to_llm(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="new answer")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=ChatSummary(
                text="User likes concise answers.",
                updated_at="2026-04-15T10:00:00+00:00",
            ),
            entries=[],
        )
        service = MessageService(ollama_client, history_client)

        await service.generate_reply("new question", 123)

        llm_messages = ollama_client.generate_reply.await_args.args[0]
        self.assertEqual(
            [(message.role, message.content) for message in llm_messages],
            [
                (
                    "system",
                    AGENT_SYSTEM_PROMPT.format(
                        agent_role="опытный программист",
                    ),
                ),
                (
                    "system",
                    "Previous conversation summary:\nUser likes concise answers.",
                ),
                ("user", "new question"),
            ],
        )

    async def test_generate_reply_summarizes_history_before_main_request(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(text=" compact summary "),
            AssistantMessage(text=" final answer "),
        ]
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=self._build_history_entries(SUMMARY_TRIGGER_ENTRIES),
        )
        service = MessageService(ollama_client, history_client)

        reply_text = await service.generate_reply("new question", 123)

        self.assertEqual(reply_text, "final answer")
        self.assertEqual(ollama_client.generate_reply.await_count, 2)
        summary_messages = ollama_client.generate_reply.await_args_list[0].args[0]
        main_messages = ollama_client.generate_reply.await_args_list[1].args[0]
        self.assertEqual(summary_messages[0].role, "system")
        self.assertIn("question-0", self._join_contents(summary_messages))
        self.assertNotIn("new question", self._join_contents(summary_messages))
        self.assertEqual(
            [(message.role, message.content) for message in main_messages],
            [
                (
                    "system",
                    AGENT_SYSTEM_PROMPT.format(
                        agent_role="опытный программист",
                    ),
                ),
                ("system", "Previous conversation summary:\ncompact summary"),
                ("user", "new question"),
            ],
        )
        user_id, summary, summarized_entry_count = (
            history_client.save_summary.await_args.args
        )
        self.assertEqual(user_id, 123)
        self.assertEqual(summary.text, "compact summary")
        self.assertEqual(summarized_entry_count, SUMMARY_TRIGGER_ENTRIES)

    async def test_generate_reply_updates_existing_summary(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(text="updated summary"),
            AssistantMessage(text="final answer"),
        ]
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=ChatSummary(
                text="previous summary",
                updated_at="2026-04-15T10:00:00+00:00",
            ),
            entries=self._build_history_entries(SUMMARY_TRIGGER_ENTRIES),
        )
        service = MessageService(ollama_client, history_client)

        await service.generate_reply("new question", 123)

        summary_messages = ollama_client.generate_reply.await_args_list[0].args[0]
        self.assertIn("previous summary", self._join_contents(summary_messages))

    async def test_generate_reply_logs_summary_request_and_response(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(text="summary text"),
            AssistantMessage(text="final answer"),
        ]
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=self._build_history_entries(SUMMARY_TRIGGER_ENTRIES),
        )
        service = MessageService(ollama_client, history_client)

        with self.assertLogs(
            "talking_telegram_bot.services.message_service",
            level="INFO",
        ) as logs:
            await service.generate_reply("new question", 123)

        joined_logs = "\n".join(logs.output)
        self.assertIn("### LLM Summary Request", joined_logs)
        self.assertIn("| Entry Count | 5 |", joined_logs)
        self.assertIn("### LLM Summary Response", joined_logs)
        self.assertIn("| Summary Length | 12 |", joined_logs)
        self.assertIn("| summary | summary text |", joined_logs)

    async def test_generate_reply_uses_updated_agent_role(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="hello")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[],
        )
        service = MessageService(ollama_client, history_client)
        service.set_agent_role("системный аналитик")

        await service.generate_reply("hi", 123)

        llm_messages = ollama_client.generate_reply.await_args.args[0]
        self.assertEqual(
            (llm_messages[0].role, llm_messages[0].content),
            (
                "system",
                AGENT_SYSTEM_PROMPT.format(agent_role="системный аналитик"),
            ),
        )

    def test_set_agent_role_raises_for_empty_value(self) -> None:
        service = MessageService(AsyncMock(), AsyncMock())

        with self.assertRaises(AgentRoleSelectionError):
            service.set_agent_role("   ")

    async def test_generate_reply_raises_for_empty_summary(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="   ")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=self._build_history_entries(SUMMARY_TRIGGER_ENTRIES),
        )
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("new question", 123)

        history_client.save_summary.assert_not_awaited()
        history_client.append_entry.assert_not_awaited()

    async def test_generate_reply_raises_for_empty_response(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="   ")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[],
        )
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    async def test_generate_reply_maps_client_errors(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = OllamaClientError("down")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[],
        )
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    async def test_generate_reply_maps_history_errors(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="hello")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=[],
        )
        history_client.append_entry.side_effect = ChatHistoryClientError("down")
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    async def test_generate_reply_maps_summary_write_errors(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="summary")
        history_client = AsyncMock()
        history_client.read_history.return_value = ChatHistoryLog(
            summary=None,
            entries=self._build_history_entries(SUMMARY_TRIGGER_ENTRIES),
        )
        history_client.save_summary.side_effect = ChatHistoryClientError("down")
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

        history_client.append_entry.assert_not_awaited()

    async def test_generate_reply_maps_history_read_errors(self) -> None:
        ollama_client = AsyncMock()
        history_client = AsyncMock()
        history_client.read_history.side_effect = ChatHistoryClientError("down")
        service = MessageService(ollama_client, history_client)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

        ollama_client.generate_reply.assert_not_awaited()

    def _build_history_entries(self, count: int) -> list[ChatHistoryEntry]:
        return [
            ChatHistoryEntry(
                request=f"question-{index}",
                response=f"answer-{index}",
                created_at=f"2026-04-15T10:{index:02d}:00+00:00",
            )
            for index in range(count)
        ]

    def _join_contents(self, messages) -> str:
        return "\n".join(message.content for message in messages)
