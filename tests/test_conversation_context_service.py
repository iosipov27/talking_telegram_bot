from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from talking_telegram_bot.clients.chat_history_client import ChatHistoryClient
from talking_telegram_bot.models.messages import ChatHistoryEntry, ChatSummary
from talking_telegram_bot.services.conversation_context_service import (
    ConversationContextService,
)


class ConversationContextServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_build_context_messages_includes_summary_and_complete_pairs(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            service = ConversationContextService(ChatHistoryClient(Path(directory)))
            await service.save_summary(
                123,
                ChatSummary(
                    text="User likes concise answers.",
                    updated_at="2026-04-15T10:00:00+00:00",
                ),
                0,
            )
            await service.append_entry(
                123,
                ChatHistoryEntry(
                    request="old request",
                    response="old response",
                    created_at="2026-04-15T10:01:00+00:00",
                ),
            )
            await service.append_entry(
                123,
                ChatHistoryEntry(
                    request="orphan request",
                    response="",
                    created_at="2026-04-15T10:02:00+00:00",
                ),
            )

            messages = await service.build_context_messages(123)

            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[0].role, "system")
            self.assertIn("User likes concise answers.", messages[0].content)
            self.assertEqual(messages[1].role, "user")
            self.assertEqual(messages[1].content, "old request")
            self.assertEqual(messages[2].role, "assistant")
            self.assertEqual(messages[2].content, "old response")

    async def test_build_context_messages_pairs_legacy_split_entries(self) -> None:
        with TemporaryDirectory() as directory:
            service = ConversationContextService(ChatHistoryClient(Path(directory)))
            await service.append_entry(
                123,
                ChatHistoryEntry(
                    request="legacy request",
                    response="",
                    created_at="2026-04-15T10:01:00+00:00",
                ),
            )
            await service.append_entry(
                123,
                ChatHistoryEntry(
                    request="",
                    response="legacy response",
                    created_at="2026-04-15T10:02:00+00:00",
                ),
            )

            messages = await service.build_context_messages(123)

            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[0].content, "legacy request")
            self.assertEqual(messages[1].role, "assistant")
            self.assertEqual(messages[1].content, "legacy response")
