from __future__ import annotations

import logging
from uuid import uuid4

from telegram import Update
from telegram.ext import ContextTypes

from talking_telegram_bot.bus.command_bus import InMemoryCommandBus
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.user_messages import SAFE_LLM_ERROR_MESSAGE
from talking_telegram_bot.logging_utils import MarkdownTable, format_markdown_event
from talking_telegram_bot.messages.commands import ProcessTextMessage
from talking_telegram_bot.messages.events import UserFacingErrorRaised

logger = logging.getLogger(__name__)


class TelegramTextController:
    def __init__(
        self,
        command_bus: InMemoryCommandBus,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._command_bus = command_bus
        self._event_bus = event_bus

    async def handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del context
        message = update.effective_message
        if message is None or message.text is None:
            return
        self._log_text_message_received(update, message.text)
        user_id = self._get_user_id(update)
        if user_id is None:
            logger.warning(log_events.TEXT_MESSAGE_USER_ID_MISSING)
            await self._send_direct_reply(message, SAFE_LLM_ERROR_MESSAGE)
            return
        correlation_id = str(uuid4())
        try:
            await self._command_bus.execute(
                ProcessTextMessage(message=message, raw_text=message.text),
                correlation_id=correlation_id,
                chat_id=self._get_chat_id(update),
                user_id=user_id,
            )
        except Exception:
            logger.exception(log_events.UNEXPECTED_TELEGRAM_HANDLER_ERROR)
            await self._event_bus.publish_and_wait(
                UserFacingErrorRaised(
                    text=SAFE_LLM_ERROR_MESSAGE,
                    fallback_message=message,
                ),
                correlation_id=correlation_id,
                chat_id=self._get_chat_id(update),
                user_id=user_id,
            )

    def _log_text_message_received(self, update: Update, text: str) -> None:
        logger.info(
            format_markdown_event(
                log_events.TEXT_MESSAGE_RECEIVED,
                [
                    ("Chat ID", self._get_chat_id(update)),
                    ("User ID", self._get_user_id(update)),
                    ("Text Length", len(text)),
                ],
                detail_tables=[
                    MarkdownTable(
                        headers=("Role", "Content"),
                        rows=(("user", text),),
                    ),
                ],
            ),
        )

    async def _send_direct_reply(self, message, text: str) -> None:
        try:
            await message.reply_text(text)
        except Exception:
            logger.exception(log_events.TELEGRAM_REPLY_SEND_FAILED)

    def _get_chat_id(self, update: Update) -> int | None:
        chat = getattr(update, "effective_chat", None)
        return getattr(chat, "id", None)

    def _get_user_id(self, update: Update) -> int | None:
        user = getattr(update, "effective_user", None)
        return getattr(user, "id", None)

