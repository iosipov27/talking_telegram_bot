from __future__ import annotations

import logging
from dataclasses import dataclass
from time import monotonic

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.telegram import MODEL_CALLBACK_PREFIX
from talking_telegram_bot.constants.user_messages import (
    CURRENT_MODEL_BUTTON_LABEL,
    LLM_THINKING_MESSAGE,
    MODEL_LIST_MESSAGE,
)
from talking_telegram_bot.logging_utils import MarkdownTable, format_markdown_event
from talking_telegram_bot.messages.events import (
    CallbackTextRequested,
    ModelListReady,
    ProgressUpdated,
    ReplyReady,
    StartTelegramResponseSession,
    TextReplyRequested,
    UserFacingErrorRaised,
)

logger = logging.getLogger(__name__)


@dataclass
class _TelegramResponseSession:
    message: object
    started_at: float
    progress_message: object | None = None
    current_text: str = LLM_THINKING_MESSAGE


class TelegramOutboundController:
    def __init__(self) -> None:
        self._sessions: dict[str, _TelegramResponseSession] = {}

    async def handle(self, envelope: MessageEnvelope[object]) -> None:
        message = envelope.message
        if isinstance(message, StartTelegramResponseSession):
            await self._handle_session_started(envelope)
            return
        if isinstance(message, ProgressUpdated):
            await self._handle_progress_updated(envelope)
            return
        if isinstance(message, ReplyReady):
            await self._handle_reply_ready(envelope)
            return
        if isinstance(message, UserFacingErrorRaised):
            await self._handle_user_facing_error(envelope)
            return
        if isinstance(message, TextReplyRequested):
            await self._send_reply(message.message, message.text)
            return
        if isinstance(message, CallbackTextRequested):
            await self._edit_callback_text(message.callback_query, message.text)
            return
        if isinstance(message, ModelListReady):
            await self._handle_model_list_ready(envelope)

    async def _handle_session_started(
        self,
        envelope: MessageEnvelope[StartTelegramResponseSession],
    ) -> None:
        session = _TelegramResponseSession(
            message=envelope.message.message,
            started_at=monotonic(),
        )
        self._sessions[envelope.correlation_id] = session
        try:
            session.progress_message = await envelope.message.message.reply_text(
                LLM_THINKING_MESSAGE,
            )
        except Exception:
            logger.exception(log_events.TELEGRAM_THINKING_MESSAGE_SEND_FAILED)

    async def _handle_progress_updated(
        self,
        envelope: MessageEnvelope[ProgressUpdated],
    ) -> None:
        session = self._sessions.get(envelope.correlation_id)
        if session is None or session.progress_message is None:
            return
        if envelope.message.text == session.current_text:
            return
        try:
            await session.progress_message.edit_text(envelope.message.text)
        except Exception:
            logger.exception(log_events.TELEGRAM_THINKING_MESSAGE_EDIT_FAILED)
            return
        session.current_text = envelope.message.text

    async def _handle_reply_ready(
        self,
        envelope: MessageEnvelope[ReplyReady],
    ) -> None:
        session = self._sessions.pop(envelope.correlation_id, None)
        if session is None:
            return
        await self._stop_progress_message(session.progress_message)
        await self._send_reply(session.message, envelope.message.text)
        self._log_processing_finished(
            correlation_id=envelope.correlation_id,
            reply_text=envelope.message.text,
            started_at=session.started_at,
        )

    async def _handle_user_facing_error(
        self,
        envelope: MessageEnvelope[UserFacingErrorRaised],
    ) -> None:
        session = self._sessions.pop(envelope.correlation_id, None)
        if session is not None:
            await self._stop_progress_message(session.progress_message)
            await self._send_reply(session.message, envelope.message.text)
            return
        if envelope.message.fallback_message is not None:
            await self._send_reply(envelope.message.fallback_message, envelope.message.text)

    async def _handle_model_list_ready(
        self,
        envelope: MessageEnvelope[ModelListReady],
    ) -> None:
        await envelope.message.message.reply_text(
            text=MODEL_LIST_MESSAGE.format(current_model=envelope.message.current_model),
            reply_markup=self._build_model_keyboard(
                envelope.message.current_model,
                envelope.message.model_names,
            ),
        )
        logger.info(
            format_markdown_event(
                log_events.MODEL_LIST_SENT,
                [
                    ("Current Model", envelope.message.current_model),
                    ("Model Count", len(envelope.message.model_names)),
                ],
                detail_tables=[
                    MarkdownTable(
                        headers=("#", "Model"),
                        rows=tuple(
                            (index, model_name)
                            for index, model_name in enumerate(
                                envelope.message.model_names,
                                start=1,
                            )
                        ),
                    ),
                ],
            ),
        )

    async def _send_reply(self, message, text: str) -> None:
        try:
            await message.reply_text(text)
            logger.info(
                format_markdown_event(
                    log_events.TELEGRAM_REPLY_SENT,
                    [("Text Length", len(text))],
                    detail_tables=[
                        MarkdownTable(
                            headers=("Role", "Content"),
                            rows=(("assistant", text),),
                        ),
                    ],
                ),
            )
        except Exception:
            logger.exception(log_events.TELEGRAM_REPLY_SEND_FAILED)

    async def _edit_callback_text(self, query, text: str) -> None:
        try:
            await query.edit_message_text(text)
        except Exception:
            logger.exception(log_events.TELEGRAM_REPLY_SEND_FAILED)

    async def _stop_progress_message(self, progress_message) -> None:
        if progress_message is None:
            return
        try:
            await progress_message.delete()
        except Exception:
            logger.exception(log_events.TELEGRAM_THINKING_MESSAGE_DELETE_FAILED)

    def _build_model_keyboard(
        self,
        current_model: str,
        model_names: list[str],
    ) -> InlineKeyboardMarkup:
        rows = []
        for index, model_name in enumerate(model_names):
            label = self._format_model_button_label(current_model, model_name)
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"{MODEL_CALLBACK_PREFIX}{index}",
                    ),
                ],
            )
        return InlineKeyboardMarkup(rows)

    def _format_model_button_label(
        self,
        current_model: str,
        model_name: str,
    ) -> str:
        if model_name == current_model:
            return CURRENT_MODEL_BUTTON_LABEL.format(model_name=model_name)
        return model_name

    def _log_processing_finished(
        self,
        correlation_id: str,
        reply_text: str,
        started_at: float,
    ) -> None:
        logger.info(
            format_markdown_event(
                log_events.TEXT_MESSAGE_PROCESSED,
                [
                    ("Correlation ID", correlation_id),
                    ("Reply Length", len(reply_text)),
                    ("Elapsed Seconds", f"{monotonic() - started_at:.3f}"),
                ],
            ),
        )
