from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from talking_telegram_bot.bus.dead_letter import DeadLetterWriter
from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.registry import HandlerRegistry
from talking_telegram_bot.logging_utils import logging_context
from talking_telegram_bot.sentry_utils import capture_exception

_SENTINEL = object()


@dataclass(slots=True)
class _PendingCommand:
    envelope: MessageEnvelope[Any]
    future: asyncio.Future[Any] | None = None


class InMemoryCommandBus:
    def __init__(
        self,
        registry: HandlerRegistry | None = None,
        dead_letter_writer: DeadLetterWriter | None = None,
        worker_count: int = 1,
    ) -> None:
        self._registry = registry or HandlerRegistry()
        self._dead_letter_writer = dead_letter_writer or DeadLetterWriter()
        self._worker_count = max(1, worker_count)
        self._queue: asyncio.Queue[_PendingCommand | object] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._startup_lock = asyncio.Lock()
        self._started = False

    def register_handler(self, message_type: type[Any], handler: Any) -> None:
        self._registry.register_command_handler(message_type, handler)

    async def start(self) -> None:
        if self._started:
            return
        async with self._startup_lock:
            if self._started:
                return
            self._workers = [
                asyncio.create_task(
                    self._run_worker(index),
                    name=f"command-bus-worker-{index}",
                )
                for index in range(self._worker_count)
            ]
            self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        async with self._startup_lock:
            if not self._started:
                return
            workers = tuple(self._workers)
            self._workers.clear()
            self._started = False
            for _ in workers:
                await self._queue.put(_SENTINEL)
        await asyncio.gather(*workers, return_exceptions=True)

    async def execute(
        self,
        message: Any,
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
    ) -> Any:
        await self.start()
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self._queue.put(
            _PendingCommand(
                envelope=self._build_envelope(
                    message=message,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    chat_id=chat_id,
                    user_id=user_id,
                ),
                future=future,
            ),
        )
        return await future

    async def dispatch(
        self,
        message: Any,
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
    ) -> None:
        await self.start()
        await self._queue.put(
            _PendingCommand(
                envelope=self._build_envelope(
                    message=message,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    chat_id=chat_id,
                    user_id=user_id,
                ),
            ),
        )

    def _build_envelope(
        self,
        *,
        message: Any,
        correlation_id: str | None,
        causation_id: str | None,
        chat_id: int | None,
        user_id: int | None,
    ) -> MessageEnvelope[Any]:
        return MessageEnvelope(
            message=message,
            correlation_id=correlation_id or str(uuid4()),
            causation_id=causation_id,
            chat_id=chat_id,
            user_id=user_id,
        )

    async def _run_worker(self, worker_index: int) -> None:
        del worker_index
        while True:
            queued_item = await self._queue.get()
            if queued_item is _SENTINEL:
                self._queue.task_done()
                return
            try:
                with logging_context(
                    trace_id=queued_item.envelope.correlation_id,
                    request_id=queued_item.envelope.correlation_id,
                    chat_id=queued_item.envelope.chat_id,
                    user_id=queued_item.envelope.user_id,
                    envelope_id=queued_item.envelope.message_id,
                    causation_id=queued_item.envelope.causation_id,
                ):
                    handler = self._registry.get_command_handler(
                        queued_item.envelope.message,
                    )
                    result = await handler.handle(queued_item.envelope)
            except Exception as exc:
                capture_exception(
                    exc,
                    trace_id=queued_item.envelope.correlation_id,
                    request_id=queued_item.envelope.correlation_id,
                    chat_id=queued_item.envelope.chat_id,
                    user_id=queued_item.envelope.user_id,
                    envelope_id=queued_item.envelope.message_id,
                    causation_id=queued_item.envelope.causation_id,
                )
                await self._dead_letter_writer.write(queued_item.envelope, exc)
                if queued_item.future is not None and not queued_item.future.done():
                    queued_item.future.set_exception(exc)
            else:
                if queued_item.future is not None and not queued_item.future.done():
                    queued_item.future.set_result(result)
            finally:
                self._queue.task_done()
