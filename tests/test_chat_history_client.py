from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from talking_telegram_bot.clients.chat_history_client import ChatHistoryClient
from talking_telegram_bot.models.messages import ChatHistoryEntry


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

    async def test_read_entries_returns_empty_list_for_new_user(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = ChatHistoryClient(Path(directory))

            entries = await client.read_entries(123)

            self.assertEqual(entries, [])

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
