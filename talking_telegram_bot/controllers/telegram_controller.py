from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from talking_telegram_bot.services.message_service import (
    MessageProcessingError,
    MessageService,
)

logger = logging.getLogger(__name__)

SAFE_ERROR_MESSAGE = "LLM is currently unavailable. Please try again later."


class TelegramMessageController:
    def __init__(self, message_service: MessageService) -> None:
        self._message_service = message_service

    async def handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del context
        message = update.effective_message
        if message is None or message.text is None:
            return
        try:
            reply_text = await self._message_service.generate_reply(message.text)
        except MessageProcessingError as exc:
            logger.warning("Failed to process message: %s", exc)
            await self._send_reply(message, SAFE_ERROR_MESSAGE)
            return
        except Exception:
            logger.exception("Unexpected error while handling Telegram message.")
            await self._send_reply(message, SAFE_ERROR_MESSAGE)
            return
        await self._send_reply(message, reply_text)

    async def _send_reply(self, message, text: str) -> None:
        try:
            await message.reply_text(text)
        except Exception:
            logger.exception("Failed to send Telegram reply.")
