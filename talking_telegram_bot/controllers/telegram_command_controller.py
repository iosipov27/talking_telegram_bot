from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from talking_telegram_bot.bus.command_bus import InMemoryCommandBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import format_markdown_event
from talking_telegram_bot.messages.commands import ListModels, ShowRole, UpdateRole

logger = logging.getLogger(__name__)


class TelegramCommandController:
    def __init__(self, command_bus: InMemoryCommandBus) -> None:
        self._command_bus = command_bus

    async def handle_models_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del context
        message = update.effective_message
        if message is None:
            return
        logger.info(
            format_markdown_event(
                log_events.MODELS_COMMAND_RECEIVED,
                [
                    ("Chat ID", self._get_chat_id(update)),
                    ("User ID", self._get_user_id(update)),
                ],
            ),
        )
        await self._command_bus.execute(
            ListModels(message=message),
            chat_id=self._get_chat_id(update),
            user_id=self._get_user_id(update),
        )

    async def handle_role_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        message = update.effective_message
        if message is None:
            return
        requested_role = self._read_command_argument(context)
        logger.info(
            format_markdown_event(
                log_events.ROLE_COMMAND_RECEIVED,
                [
                    ("Chat ID", self._get_chat_id(update)),
                    ("User ID", self._get_user_id(update)),
                    ("Requested Role", requested_role or "(not provided)"),
                ],
            ),
        )
        command = (
            UpdateRole(message=message, raw_role=requested_role)
            if requested_role
            else ShowRole(message=message)
        )
        await self._command_bus.execute(
            command,
            chat_id=self._get_chat_id(update),
            user_id=self._get_user_id(update),
        )

    def _read_command_argument(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        args = getattr(context, "args", None)
        if not args:
            return ""
        return " ".join(args).strip()

    def _get_chat_id(self, update: Update) -> int | None:
        chat = getattr(update, "effective_chat", None)
        return getattr(chat, "id", None)

    def _get_user_id(self, update: Update) -> int | None:
        user = getattr(update, "effective_user", None)
        return getattr(user, "id", None)
