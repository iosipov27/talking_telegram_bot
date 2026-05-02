from __future__ import annotations

import io
import json
import logging
import unittest
from dataclasses import dataclass

from talking_telegram_bot.bus.command_bus import InMemoryCommandBus
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.logging_utils import JsonLogFormatter, log_event


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


class _LoggingCommandHandler:
    async def handle(self, envelope) -> str:
        del envelope
        log_event(logging.getLogger("tests.bus"), logging.INFO, "handled")
        return "ok"


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

    async def test_command_bus_sets_logging_trace_context(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLogFormatter())
        logger = logging.getLogger("tests.bus")
        old_level = logger.level
        old_propagate = logger.propagate
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        bus = InMemoryCommandBus(worker_count=2)
        bus.register_handler(PingCommand, _LoggingCommandHandler())
        try:
            await bus.execute(
                PingCommand("hello"),
                correlation_id="corr-3",
                chat_id=10,
                user_id=20,
            )
        finally:
            await bus.stop()
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            logger.propagate = old_propagate

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["trace_id"], "corr-3")
        self.assertEqual(payload["request_id"], "corr-3")
        self.assertEqual(payload["chat_id"], 10)
        self.assertEqual(payload["user_id"], 20)
        self.assertRegex(payload["envelope_id"], r".+")
