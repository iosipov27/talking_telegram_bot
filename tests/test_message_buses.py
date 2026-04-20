from __future__ import annotations

import unittest
from dataclasses import dataclass

from talking_telegram_bot.bus.command_bus import InMemoryCommandBus
from talking_telegram_bot.bus.event_bus import InMemoryEventBus


@dataclass(frozen=True, slots=True)
class PingCommand:
    value: str


@dataclass(frozen=True, slots=True)
class PingEvent:
    value: str


class _PingCommandHandler:
    def __init__(self) -> None:
        self.seen = []

    async def handle(self, envelope) -> str:
        self.seen.append((envelope.message.value, envelope.correlation_id, envelope.user_id))
        return envelope.message.value.upper()


class _PingEventSubscriber:
    def __init__(self) -> None:
        self.seen = []

    async def handle(self, envelope) -> None:
        self.seen.append((envelope.message.value, envelope.correlation_id, envelope.chat_id))


class MessageBusTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_command_bus_executes_registered_handler(self) -> None:
        bus = InMemoryCommandBus(worker_count=2)
        handler = _PingCommandHandler()
        bus.register_handler(PingCommand, handler)

        result = await bus.execute(
            PingCommand("hello"),
            correlation_id="corr-1",
            user_id=42,
        )

        self.assertEqual(result, "HELLO")
        self.assertEqual(handler.seen, [("hello", "corr-1", 42)])
        await bus.stop()

    async def test_event_bus_publishes_to_registered_subscriber(self) -> None:
        bus = InMemoryEventBus(worker_count=2)
        subscriber = _PingEventSubscriber()
        bus.subscribe(PingEvent, subscriber)

        await bus.publish_and_wait(
            PingEvent("hello"),
            correlation_id="corr-2",
            chat_id=7,
        )

        self.assertEqual(subscriber.seen, [("hello", "corr-2", 7)])
        await bus.stop()

