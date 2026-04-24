from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.clients.chat_history_client import ChatHistoryClient
from talking_telegram_bot.handlers.history_event_subscriber import HistoryEventSubscriber
from talking_telegram_bot.messages.events import MessageReceived, ResponseGenerated
from talking_telegram_bot.services.conversation_context_service import (
    ConversationContextService,
)


class HistoryEventSubscriberTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_subscriber_persists_received_and_generated_messages(self) -> None:
        with TemporaryDirectory() as directory:
            event_bus = InMemoryEventBus(worker_count=2)
            conversation_context_service = ConversationContextService(
                ChatHistoryClient(Path(directory)),
            )
            subscriber = HistoryEventSubscriber(conversation_context_service)
            event_bus.subscribe(MessageReceived, subscriber)
            event_bus.subscribe(ResponseGenerated, subscriber)

            await event_bus.publish_and_wait(
                MessageReceived(text="hello"),
                correlation_id="corr-1",
                user_id=123,
            )
            await event_bus.publish_and_wait(
                ResponseGenerated(text="world"),
                correlation_id="corr-1",
                user_id=123,
            )

            history_log = await conversation_context_service.read_history(123)

            self.assertEqual(len(history_log.entries), 1)
            self.assertEqual(history_log.entries[0].request, "hello")
            self.assertEqual(history_log.entries[0].response, "world")
            self.assertIsNone(history_log.summary)
            await event_bus.stop()
