from __future__ import annotations

from collections import defaultdict
from typing import Any


class HandlerRegistry:
    def __init__(self) -> None:
        self._command_handlers: dict[type[Any], Any] = {}
        self._event_subscribers: dict[type[Any], list[Any]] = defaultdict(list)

    def register_command_handler(
        self,
        message_type: type[Any],
        handler: Any,
    ) -> None:
        self._command_handlers[message_type] = handler

    def register_event_subscriber(
        self,
        message_type: type[Any],
        subscriber: Any,
    ) -> None:
        self._event_subscribers[message_type].append(subscriber)

    def get_command_handler(self, message: Any) -> Any:
        message_type = type(message)
        if message_type in self._command_handlers:
            return self._command_handlers[message_type]
        raise LookupError(f"No command handler registered for {message_type.__name__}.")

    def get_event_subscribers(self, message: Any) -> list[Any]:
        return list(self._event_subscribers.get(type(message), ()))

