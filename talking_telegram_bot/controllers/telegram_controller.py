from __future__ import annotations

import logging
from time import monotonic

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from talking_telegram_bot.services.model_service import ModelSelectionError, ModelService
from talking_telegram_bot.services.message_service import (
    MessageProcessingError,
    MessageService,
)

logger = logging.getLogger(__name__)

SAFE_ERROR_MESSAGE = "LLM is currently unavailable. Please try again later."
SAFE_MODEL_ERROR_MESSAGE = "Model list is currently unavailable. Please try again later."
MODEL_CALLBACK_PREFIX = "select_model:"


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
            "Telegram text message received. chat_id=%s user_id=%s text_length=%s",
            self._get_chat_id(update),
            self._get_user_id(update),
            len(message.text),
        )
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
            "Telegram /models command received. chat_id=%s user_id=%s",
            self._get_chat_id(update),
            self._get_user_id(update),
        )
        try:
            available_models = await self._model_service.list_models()
        except ModelSelectionError as exc:
            logger.warning("Failed to list Ollama models: %s", exc)
            await self._send_reply(message, SAFE_MODEL_ERROR_MESSAGE)
            return
        await message.reply_text(
            text=self._format_model_list(available_models.current_model),
            reply_markup=self._build_model_keyboard(
                available_models.current_model,
                available_models.model_names,
            ),
        )
        logger.info("Ollama model list sent. model_count=%s", len(available_models.model_names))

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
            "Telegram model selection received. user_id=%s",
            self._get_user_id(update),
        )
        try:
            selected_model = await self._select_model_from_callback(query.data)
        except ModelSelectionError as exc:
            logger.warning("Failed to select Ollama model: %s", exc)
            await query.edit_message_text(SAFE_MODEL_ERROR_MESSAGE)
            return
        await query.edit_message_text(f"Current Ollama model: {selected_model}")
        logger.info("Ollama model switched. model=%s", selected_model)

    async def _send_reply(self, message, text: str) -> None:
        try:
            await message.reply_text(text)
            logger.info("Telegram reply sent. text_length=%s", len(text))
        except Exception:
            logger.exception("Failed to send Telegram reply.")

    def _log_text_message_processed(self, started_at: float, reply_text: str) -> None:
        elapsed_seconds = monotonic() - started_at
        logger.info(
            "Telegram text message processed. reply_length=%s elapsed_seconds=%.3f",
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
        return f"Current Ollama model: {current_model}\nSelect a model:"

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
            return f"Current: {model_name}"
        return model_name
