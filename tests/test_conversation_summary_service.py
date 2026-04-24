from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.clients.chat_history_client import ChatHistoryClient
from talking_telegram_bot.constants.summary_settings import SUMMARY_TRIGGER_ENTRIES
from talking_telegram_bot.models.messages import (
    AssistantMessage,
    ChatHistoryEntry,
    ChatSummary,
)
from talking_telegram_bot.services.conversation_context_service import (
    ConversationContextService,
)
from talking_telegram_bot.services.conversation_summary_service import (
    ConversationSummaryService,
)


class ConversationSummaryServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_summarize_if_needed_updates_summary_and_removes_old_entries(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            context_service = ConversationContextService(
                ChatHistoryClient(Path(directory)),
            )
            await context_service.save_summary(
                123,
                ChatSummary(
                    text="existing summary",
                    updated_at="2026-04-15T10:00:00+00:00",
                ),
                0,
            )
            for index in range(SUMMARY_TRIGGER_ENTRIES):
                await context_service.append_entry(
                    123,
                    ChatHistoryEntry(
                        request=f"request-{index}",
                        response=f"response-{index}",
                        created_at=f"2026-04-15T10:0{index}:00+00:00",
                    ),
                )
            ollama_client = AsyncMock()
            ollama_client.generate_reply.return_value = AssistantMessage(
                text="new compact summary",
            )
            service = ConversationSummaryService(context_service, ollama_client)

            await service.summarize_if_needed(123)

            history_log = await context_service.read_history(123)
            self.assertEqual(history_log.summary.text, "new compact summary")
            self.assertEqual(history_log.entries, [])
            request_messages = ollama_client.generate_reply.await_args.args[0]
            self.assertIn("existing summary", request_messages[1].content)

    async def test_summarize_if_needed_skips_below_threshold(self) -> None:
        with TemporaryDirectory() as directory:
            context_service = ConversationContextService(
                ChatHistoryClient(Path(directory)),
            )
            await context_service.append_entry(
                123,
                ChatHistoryEntry(
                    request="request",
                    response="response",
                    created_at="2026-04-15T10:00:00+00:00",
                ),
            )
            ollama_client = AsyncMock()
            service = ConversationSummaryService(context_service, ollama_client)

            await service.summarize_if_needed(123)

            ollama_client.generate_reply.assert_not_called()

    async def test_summarize_if_needed_compacts_legacy_split_entries(self) -> None:
        with TemporaryDirectory() as directory:
            context_service = ConversationContextService(
                ChatHistoryClient(Path(directory)),
            )
            for index in range(SUMMARY_TRIGGER_ENTRIES):
                await context_service.append_entry(
                    123,
                    ChatHistoryEntry(
                        request=f"request-{index}",
                        response="",
                        created_at=f"2026-04-15T10:0{index}:00+00:00",
                    ),
                )
                await context_service.append_entry(
                    123,
                    ChatHistoryEntry(
                        request="",
                        response=f"response-{index}",
                        created_at=f"2026-04-15T10:0{index}:01+00:00",
                    ),
                )
            ollama_client = AsyncMock()
            ollama_client.generate_reply.return_value = AssistantMessage(
                text="legacy compact summary",
            )
            service = ConversationSummaryService(context_service, ollama_client)

            await service.summarize_if_needed(123)

            history_log = await context_service.read_history(123)
            self.assertEqual(history_log.summary.text, "legacy compact summary")
            self.assertEqual(history_log.entries, [])
