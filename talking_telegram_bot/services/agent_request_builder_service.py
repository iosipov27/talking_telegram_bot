from __future__ import annotations

from datetime import datetime
from typing import Callable

from talking_telegram_bot.models.messages import ConversationMessage


class AgentRequestBuilderService:
    def __init__(
        self,
        datetime_provider: Callable[[], str] | None = None,
    ) -> None:
        self._datetime_provider = datetime_provider

    def build_request_messages(
        self,
        messages: list[ConversationMessage],
    ) -> list[ConversationMessage]:
        current_datetime_message = self.build_current_datetime_message()
        if not messages:
            return [current_datetime_message]
        first_message, *other_messages = messages
        if first_message.role != "system":
            return [current_datetime_message, *messages]
        return [first_message, current_datetime_message, *other_messages]

    def build_current_datetime_message(self) -> ConversationMessage:
        return ConversationMessage(
            role="system",
            content=(
                "Текущие локальные дата и время: "
                f"{self.get_current_datetime_iso()}. "
                "Используй это как ориентир для дат и времени, когда встречаются "
                "слова вроде сегодня, завтра, вчера, сейчас, текущий и последний."
            ),
        )

    def get_current_datetime_iso(self) -> str:
        if self._datetime_provider is not None:
            return self._datetime_provider()
        return datetime.now().astimezone().isoformat(timespec="seconds")
