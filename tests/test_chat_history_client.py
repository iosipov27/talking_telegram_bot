from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from talking_telegram_bot.clients.chat_history_client import (
    ChatHistoryClient,
    MAX_CHAT_HISTORY_ENTRIES,
)
from talking_telegram_bot.models.messages import ChatHistoryEntry, ChatSummary


class ChatHistoryClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_append_entry_writes_user_history_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = ChatHistoryClient(Path(directory))
            entry = ChatHistoryEntry(
                request="hi",
                response="hello",
                created_at="2026-04-15T10:00:00+00:00",
            )

            await client.append_entry(123, entry)

            history_path = Path(directory) / "chat_history_123.json"
            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["user_id"], 123)
            self.assertEqual(payload["history"], [entry.__dict__])

    async def test_append_entry_keeps_existing_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "history": [
                            {
                                "request": "old question",
                                "response": "old answer",
                                "created_at": "2026-04-15T10:00:00+00:00",
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )
            entry = ChatHistoryEntry(
                request="new question",
                response="new answer",
                created_at="2026-04-15T10:01:00+00:00",
            )
            client = ChatHistoryClient(Path(directory))

            await client.append_entry(123, entry)

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["history"]), 2)
            self.assertEqual(payload["history"][1], entry.__dict__)

    async def test_append_entry_keeps_existing_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            summary = ChatSummary(
                text="old summary",
                updated_at="2026-04-15T10:00:00+00:00",
            )
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "summary": summary.__dict__,
                        "history": [],
                    },
                ),
                encoding="utf-8",
            )
            client = ChatHistoryClient(Path(directory))

            await client.append_entry(123, self._build_entry(1))

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"], summary.__dict__)

    async def test_append_entry_keeps_only_last_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "history": [
                            self._build_entry(index).__dict__
                            for index in range(MAX_CHAT_HISTORY_ENTRIES)
                        ],
                    },
                ),
                encoding="utf-8",
            )
            new_entry = self._build_entry(MAX_CHAT_HISTORY_ENTRIES)
            client = ChatHistoryClient(Path(directory))

            await client.append_entry(123, new_entry)

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["history"]), MAX_CHAT_HISTORY_ENTRIES)
            self.assertEqual(payload["history"][0]["request"], "request-1")
            self.assertEqual(payload["history"][-1], new_entry.__dict__)

    async def test_read_entries_returns_existing_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "history": [
                            {
                                "request": "hi",
                                "response": "hello",
                                "created_at": "2026-04-15T10:00:00+00:00",
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )
            client = ChatHistoryClient(Path(directory))

            entries = await client.read_entries(123)

            self.assertEqual(
                entries,
                [
                    ChatHistoryEntry(
                        request="hi",
                        response="hello",
                        created_at="2026-04-15T10:00:00+00:00",
                    ),
                ],
            )

    async def test_read_history_returns_summary_and_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            summary = ChatSummary(
                text="summary text",
                updated_at="2026-04-15T10:00:00+00:00",
            )
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "summary": summary.__dict__,
                        "history": [self._build_entry(1).__dict__],
                    },
                ),
                encoding="utf-8",
            )
            client = ChatHistoryClient(Path(directory))

            history_log = await client.read_history(123)

            self.assertEqual(history_log.summary, summary)
            self.assertEqual(history_log.entries, [self._build_entry(1)])

    async def test_save_summary_writes_summary_and_removes_summarized_entries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "history": [
                            self._build_entry(index).__dict__ for index in range(6)
                        ],
                    },
                ),
                encoding="utf-8",
            )
            summary = ChatSummary(
                text="compact summary",
                updated_at="2026-04-15T10:00:00+00:00",
            )
            client = ChatHistoryClient(Path(directory))

            await client.save_summary(123, summary, 5)

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"], summary.__dict__)
            self.assertEqual(
                payload["history"],
                [self._build_entry(5).__dict__],
            )

    async def test_save_summary_limits_entries_before_removing_summarized_entries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "history": [
                            self._build_entry(index).__dict__
                            for index in range(MAX_CHAT_HISTORY_ENTRIES + 2)
                        ],
                    },
                ),
                encoding="utf-8",
            )
            client = ChatHistoryClient(Path(directory))

            await client.save_summary(123, self._build_summary(), 10)

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["history"], [])

    async def test_read_entries_returns_empty_list_for_new_user(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = ChatHistoryClient(Path(directory))

            entries = await client.read_entries(123)

            self.assertEqual(entries, [])

    async def test_read_entries_returns_only_last_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "chat_history_123.json"
            history_path.write_text(
                json.dumps(
                    {
                        "user_id": 123,
                        "history": [
                            self._build_entry(index).__dict__
                            for index in range(MAX_CHAT_HISTORY_ENTRIES + 2)
                        ],
                    },
                ),
                encoding="utf-8",
            )
            client = ChatHistoryClient(Path(directory))

            entries = await client.read_entries(123)

            self.assertEqual(len(entries), MAX_CHAT_HISTORY_ENTRIES)
            self.assertEqual(entries[0].request, "request-2")
            self.assertEqual(entries[-1].request, "request-11")

    async def test_append_entry_keeps_users_in_separate_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = ChatHistoryClient(Path(directory))
            entry = ChatHistoryEntry(
                request="hi",
                response="hello",
                created_at="2026-04-15T10:00:00+00:00",
            )

            await client.append_entry(123, entry)
            await client.append_entry(456, entry)

            self.assertTrue((Path(directory) / "chat_history_123.json").exists())
            self.assertTrue((Path(directory) / "chat_history_456.json").exists())

    def _build_entry(self, index: int) -> ChatHistoryEntry:
        return ChatHistoryEntry(
            request=f"request-{index}",
            response=f"response-{index}",
            created_at=f"2026-04-15T10:{index:02d}:00+00:00",
        )

    def _build_summary(self) -> ChatSummary:
        return ChatSummary(
            text="compact summary",
            updated_at="2026-04-15T10:00:00+00:00",
        )
