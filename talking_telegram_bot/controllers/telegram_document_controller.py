from __future__ import annotations

import logging
from uuid import uuid4

from telegram import Update
from telegram.ext import ContextTypes

from talking_telegram_bot.bus.command_bus import InMemoryCommandBus
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.user_messages import (
    FILE_READ_ERROR_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
)
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.commands import ProcessDocumentMessage
from talking_telegram_bot.messages.events import UserFacingErrorRaised

logger = logging.getLogger(__name__)


class TelegramDocumentController:
    def __init__(
        self,
        command_bus: InMemoryCommandBus,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._command_bus = command_bus
        self._event_bus = event_bus

    async def handle_document_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del context
        message = update.effective_message
        if message is None:
            return
        document = getattr(message, "document", None)
        if document is None:
            return
        correlation_id = str(uuid4())
        file_name = getattr(document, "file_name", None)
        file_size = getattr(document, "file_size", None)
        self._log_document_message_received(
            update,
            file_name,
            file_size,
            correlation_id,
        )
        user_id = self._get_user_id(update)
        if user_id is None:
            log_event(
                logger,
                logging.WARNING,
                log_events.DOCUMENT_MESSAGE_USER_ID_MISSING,
                trace_id=correlation_id,
                chat_id=self._get_chat_id(update),
            )
            await self._send_direct_reply(
                message,
                SAFE_LLM_ERROR_MESSAGE,
                correlation_id,
            )
            return
        try:
            content = await self._download_document_content(document, correlation_id)
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                log_events.DOCUMENT_MESSAGE_PROCESSING_ERROR,
                trace_id=correlation_id,
                chat_id=self._get_chat_id(update),
                user_id=user_id,
                stage="download",
                exc_info=True,
            )
            await self._send_direct_reply(
                message,
                FILE_READ_ERROR_MESSAGE,
                correlation_id,
            )
            return
        try:
            await self._command_bus.execute(
                ProcessDocumentMessage(
                    message=message,
                    file_name=file_name,
                    file_size=file_size,
                    content=content,
                ),
                correlation_id=correlation_id,
                chat_id=self._get_chat_id(update),
                user_id=user_id,
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                log_events.UNEXPECTED_TELEGRAM_HANDLER_ERROR,
                trace_id=correlation_id,
                chat_id=self._get_chat_id(update),
                user_id=user_id,
                exc_info=True,
            )
            await self._event_bus.publish_and_wait(
                UserFacingErrorRaised(
                    text=SAFE_LLM_ERROR_MESSAGE,
                    fallback_message=message,
                ),
                correlation_id=correlation_id,
                chat_id=self._get_chat_id(update),
                user_id=user_id,
            )

    def _log_document_message_received(
        self,
        update: Update,
        file_name: str | None,
        file_size: int | None,
        trace_id: str,
    ) -> None:
        log_event(
            logger,
            logging.INFO,
            log_events.DOCUMENT_MESSAGE_RECEIVED,
            trace_id=trace_id,
            chat_id=self._get_chat_id(update),
            user_id=self._get_user_id(update),
            file_name=file_name or "(missing)",
            file_size=file_size or 0,
        )

    async def _send_direct_reply(self, message, text: str, trace_id: str) -> None:
        try:
            await message.reply_text(text)
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                log_events.TELEGRAM_REPLY_SEND_FAILED,
                trace_id=trace_id,
                exc_info=True,
            )

    async def _download_document_content(self, document, trace_id: str) -> bytes:
        log_event(
            logger,
            logging.INFO,
            log_events.DOCUMENT_DOWNLOAD_STARTED,
            trace_id=trace_id,
        )
        telegram_file = await document.get_file()
        content = await telegram_file.download_as_bytearray()
        log_event(
            logger,
            logging.INFO,
            log_events.DOCUMENT_DOWNLOAD_COMPLETED,
            trace_id=trace_id,
            content_length=len(content),
        )
        return bytes(content)

    def _get_chat_id(self, update: Update) -> int | None:
        chat = getattr(update, "effective_chat", None)
        return getattr(chat, "id", None)

    def _get_user_id(self, update: Update) -> int | None:
        user = getattr(update, "effective_user", None)
        return getattr(user, "id", None)
