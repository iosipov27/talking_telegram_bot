from __future__ import annotations

import logging
from time import monotonic

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.telegram import MODEL_CALLBACK_PREFIX
from talking_telegram_bot.constants.user_messages import (
    CURRENT_MODEL_BUTTON_LABEL,
    MODEL_LIST_MESSAGE,
    MODEL_SELECTED_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
    SAFE_MODEL_ERROR_MESSAGE,
)
from talking_telegram_bot.services.model_service import ModelSelectionError, ModelService
from talking_telegram_bot.services.message_service import (
    MessageProcessingError,
    MessageService,
)

logger = logging.getLogger(__name__)


class TelegramMessageController:
    def __init__(
        self,
        message_service: MessageService,
        model_service: ModelService,
    ) -> None:
        self._message_service = message_service
        self._model_service = model_service

    async def handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        del context
        message = update.effective_message
        if message is None or message.text is None:
            return
        started_at = monotonic()
        logger.info(
            log_events.TEXT_MESSAGE_RECEIVED,
            self._get_chat_id(update),
            self._get_user_id(update),
            len(message.text),
        )
        try:
            reply_text = await self._message_service.generate_reply(message.text)
        except MessageProcessingError as exc:
            logger.warning(log_events.TEXT_MESSAGE_PROCESSING_FAILED, exc)
            await self._send_reply(message, SAFE_LLM_ERROR_MESSAGE)
            return
        except Exception:
            logger.exception(log_events.UNEXPECTED_TELEGRAM_HANDLER_ERROR)
            await self._send_reply(message, SAFE_LLM_ERROR_MESSAGE)
            return
        await self._send_reply(message, reply_text)
        self._log_text_message_processed(started_at, reply_text)

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
            log_events.MODELS_COMMAND_RECEIVED,
            self._get_chat_id(update),
            self._get_user_id(update),
        )
        try:
            available_models = await self._model_service.list_models()
        except ModelSelectionError as exc:
            logger.warning(log_events.MODEL_LIST_FAILED, exc)
            await self._send_reply(message, SAFE_MODEL_ERROR_MESSAGE)
            return
        await message.reply_text(
            text=self._format_model_list(available_models.current_model),
            reply_markup=self._build_model_keyboard(
                available_models.current_model,
                available_models.model_names,
            ),
        )
        logger.info(log_events.MODEL_LIST_SENT, len(available_models.model_names))

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
            log_events.MODEL_SELECTION_RECEIVED,
            self._get_user_id(update),
        )
        try:
            selected_model = await self._select_model_from_callback(query.data)
        except ModelSelectionError as exc:
            logger.warning(log_events.MODEL_SELECTION_FAILED, exc)
            await query.edit_message_text(SAFE_MODEL_ERROR_MESSAGE)
            return
        await query.edit_message_text(
            MODEL_SELECTED_MESSAGE.format(selected_model=selected_model),
        )
        logger.info(log_events.MODEL_SWITCHED, selected_model)

    async def _send_reply(self, message, text: str) -> None:
        try:
            await message.reply_text(text)
            logger.info(log_events.TELEGRAM_REPLY_SENT, len(text))
        except Exception:
            logger.exception(log_events.TELEGRAM_REPLY_SEND_FAILED)

    def _log_text_message_processed(self, started_at: float, reply_text: str) -> None:
        elapsed_seconds = monotonic() - started_at
        logger.info(
            log_events.TEXT_MESSAGE_PROCESSED,
            len(reply_text),
            elapsed_seconds,
        )

    def _get_chat_id(self, update: Update) -> int | None:
        chat = getattr(update, "effective_chat", None)
        return getattr(chat, "id", None)

    def _get_user_id(self, update: Update) -> int | None:
        user = getattr(update, "effective_user", None)
        return getattr(user, "id", None)

    async def _select_model_from_callback(self, callback_data: str) -> str:
        raw_index = callback_data.removeprefix(MODEL_CALLBACK_PREFIX)
        try:
            model_index = int(raw_index)
        except ValueError as exc:
            raise ModelSelectionError("Model callback data is invalid.") from exc
        return await self._model_service.select_model_by_index(model_index)

    def _format_model_list(self, current_model: str) -> str:
        return MODEL_LIST_MESSAGE.format(current_model=current_model)

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
