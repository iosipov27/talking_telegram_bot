from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from talking_telegram_bot.bus.command_bus import InMemoryCommandBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.messages.commands import SelectModel

from talking_telegram_bot.logging_utils import format_markdown_event

logger = logging.getLogger(__name__)


class TelegramCallbackController:
    def __init__(self, command_bus: InMemoryCommandBus) -> None:
        self._command_bus = command_bus

    async def handle_model_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del context
        query = update.callback_query
        if query is None or query.data is None:
            return
        await query.answer()
        logger.info(
            format_markdown_event(
                log_events.MODEL_SELECTION_RECEIVED,
                [
                    ("User ID", self._get_user_id(update)),
                    ("Callback Data", query.data),
                ],
            ),
        )
        await self._command_bus.execute(
            SelectModel(
                callback_query=query,
                callback_data=query.data,
            ),
            user_id=self._get_user_id(update),
        )

    def _get_user_id(self, update: Update) -> int | None:
        user = getattr(update, "effective_user", None)
        return getattr(user, "id", None)

