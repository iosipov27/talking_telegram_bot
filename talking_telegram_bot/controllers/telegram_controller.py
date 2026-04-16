from __future__ import annotations

import logging
from dataclasses import dataclass
from time import monotonic

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.telegram import MODEL_CALLBACK_PREFIX
from talking_telegram_bot.constants.user_messages import (
    CURRENT_MODEL_BUTTON_LABEL,
    FILE_READ_ERROR_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    LLM_THINKING_MESSAGE,
    MODEL_LIST_MESSAGE,
    MODEL_SELECTED_MESSAGE,
    ROLE_MESSAGE,
    ROLE_UPDATED_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
    SAFE_MODEL_ERROR_MESSAGE,
    UNSUPPORTED_FILE_MESSAGE,
)
from talking_telegram_bot.logging_utils import MarkdownTable, format_markdown_event
from talking_telegram_bot.services.file_processing_service import (
    FileProcessingError,
    FileProcessingService,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from talking_telegram_bot.services.model_service import ModelSelectionError, ModelService
from talking_telegram_bot.services.message_service import (
    AgentRoleSelectionError,
    AgentRoleUpdateError,
    MessageProcessingError,
    MessageService,
)

logger = logging.getLogger(__name__)


@dataclass
class ProgressMessage:
    message: object
    current_text: str


class TelegramMessageController:
    def __init__(
        self,
        message_service: MessageService,
        model_service: ModelService,
        file_processing_service: FileProcessingService,
    ) -> None:
        self._message_service = message_service
        self._model_service = model_service
        self._file_processing_service = file_processing_service

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
        self._log_text_message_received(update, message.text)
        user_id = self._get_user_id(update)
        if user_id is None:
            logger.warning(log_events.TEXT_MESSAGE_USER_ID_MISSING)
            await self._send_reply(message, SAFE_LLM_ERROR_MESSAGE)
            return
        await self._reply_to_text_message(message, user_id, started_at)

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
        started_at = monotonic()
        file_name = getattr(document, "file_name", None)
        file_size = getattr(document, "file_size", None)
        self._log_document_message_received(update, file_name, file_size)
        user_id = self._get_user_id(update)
        if user_id is None:
            logger.warning(log_events.DOCUMENT_MESSAGE_USER_ID_MISSING)
            await self._send_reply(message, SAFE_LLM_ERROR_MESSAGE)
            return
        try:
            self._file_processing_service.validate_metadata(file_name, file_size)
        except UnsupportedFileTypeError as exc:
            logger.warning(log_events.DOCUMENT_MESSAGE_PROCESSING_FAILED, exc)
            await self._send_reply(message, UNSUPPORTED_FILE_MESSAGE)
            return
        except FileTooLargeError as exc:
            logger.warning(log_events.DOCUMENT_MESSAGE_PROCESSING_FAILED, exc)
            await self._send_reply(message, self._format_file_too_large_message())
            return
        await self._reply_to_document_message(
            message,
            document,
            user_id,
            started_at,
        )

    async def _reply_to_text_message(
        self,
        message,
        user_id: int,
        started_at: float,
    ) -> None:
        progress_message = await self._start_progress_message(message)
        reply_text = SAFE_LLM_ERROR_MESSAGE
        is_successful = False
        try:
            reply_text = await self._message_service.generate_reply(
                message.text,
                user_id,
                progress_callback=self._build_progress_callback(progress_message),
            )
            is_successful = True
        except MessageProcessingError as exc:
            logger.warning(log_events.TEXT_MESSAGE_PROCESSING_FAILED, exc)
        except Exception:
            logger.exception(log_events.UNEXPECTED_TELEGRAM_HANDLER_ERROR)
        finally:
            await self._stop_progress_message(progress_message)
        await self._send_reply(message, reply_text)
        if is_successful:
            self._log_text_message_processed(started_at, reply_text)

    async def _reply_to_document_message(
        self,
        message,
        document,
        user_id: int,
        started_at: float,
    ) -> None:
        progress_message = await self._start_progress_message(message)
        reply_text = SAFE_LLM_ERROR_MESSAGE
        is_successful = False
        try:
            document_content = await self._download_document_content(document)
            prompt_text = self._file_processing_service.build_llm_prompt(
                getattr(document, "file_name", None),
                document_content,
            )
            reply_text = await self._message_service.generate_reply(
                prompt_text,
                user_id,
                progress_callback=self._build_progress_callback(progress_message),
            )
            is_successful = True
        except FileTooLargeError as exc:
            logger.warning(log_events.DOCUMENT_MESSAGE_PROCESSING_FAILED, exc)
            reply_text = self._format_file_too_large_message()
        except FileProcessingError as exc:
            logger.warning(log_events.DOCUMENT_MESSAGE_PROCESSING_FAILED, exc)
            reply_text = FILE_READ_ERROR_MESSAGE
        except MessageProcessingError as exc:
            logger.warning(log_events.DOCUMENT_MESSAGE_PROCESSING_FAILED, exc)
        except Exception:
            logger.exception(log_events.UNEXPECTED_TELEGRAM_HANDLER_ERROR)
        finally:
            await self._stop_progress_message(progress_message)
        await self._send_reply(message, reply_text)
        if is_successful:
            self._log_document_message_processed(started_at, reply_text)

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
        logger.info(
            format_markdown_event(
                log_events.MODEL_LIST_SENT,
                [
                    ("Current Model", available_models.current_model),
                    ("Model Count", len(available_models.model_names)),
                ],
                detail_tables=[
                    MarkdownTable(
                        headers=("#", "Model"),
                        rows=tuple(
                            (index, model_name)
                            for index, model_name in enumerate(
                                available_models.model_names,
                                start=1,
                            )
                        ),
                    ),
                ],
            ),
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
        if not requested_role:
            await self._send_reply(message, self._format_role_message())
            return
        user_id = self._get_user_id(update)
        try:
            if user_id is None:
                selected_role = self._message_service.set_agent_role(requested_role)
            else:
                selected_role = await self._message_service.update_agent_role(
                    requested_role,
                    user_id,
                )
        except (AgentRoleSelectionError, AgentRoleUpdateError) as exc:
            logger.warning(log_events.ROLE_UPDATE_FAILED, exc)
            await self._send_reply(message, self._format_role_message())
            return
        await self._send_reply(
            message,
            ROLE_UPDATED_MESSAGE.format(agent_role=selected_role),
        )
        logger.info(
            format_markdown_event(
                log_events.ROLE_UPDATED,
                [("Selected Role", selected_role)],
            ),
        )

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
        try:
            selected_model = await self._select_model_from_callback(query.data)
        except ModelSelectionError as exc:
            logger.warning(log_events.MODEL_SELECTION_FAILED, exc)
            await query.edit_message_text(SAFE_MODEL_ERROR_MESSAGE)
            return
        await query.edit_message_text(
            MODEL_SELECTED_MESSAGE.format(selected_model=selected_model),
        )
        logger.info(
            format_markdown_event(
                log_events.MODEL_SWITCHED,
                [("Selected Model", selected_model)],
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

    async def _start_progress_message(self, message) -> ProgressMessage | None:
        try:
            progress_message = await message.reply_text(
                LLM_THINKING_MESSAGE,
            )
        except Exception:
            logger.exception(log_events.TELEGRAM_THINKING_MESSAGE_SEND_FAILED)
            return None
        return ProgressMessage(
            message=progress_message,
            current_text=LLM_THINKING_MESSAGE,
        )

    def _build_progress_callback(
        self,
        progress_message: ProgressMessage | None,
    ):
        if progress_message is None:
            return None

        async def progress_callback(text: str) -> None:
            await self._update_progress_message(progress_message, text)

        return progress_callback

    async def _update_progress_message(
        self,
        progress_message: ProgressMessage,
        text: str,
    ) -> bool:
        if text == progress_message.current_text:
            return True
        try:
            await progress_message.message.edit_text(text)
        except Exception:
            logger.exception(log_events.TELEGRAM_THINKING_MESSAGE_EDIT_FAILED)
            return False
        progress_message.current_text = text
        return True

    async def _stop_progress_message(
        self,
        progress_message: ProgressMessage | None,
    ) -> None:
        if progress_message is None:
            return
        try:
            await progress_message.message.delete()
        except Exception:
            logger.exception(log_events.TELEGRAM_THINKING_MESSAGE_DELETE_FAILED)

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

    def _log_text_message_processed(self, started_at: float, reply_text: str) -> None:
        elapsed_seconds = monotonic() - started_at
        logger.info(
            format_markdown_event(
                log_events.TEXT_MESSAGE_PROCESSED,
                [
                    ("Reply Length", len(reply_text)),
                    ("Elapsed Seconds", f"{elapsed_seconds:.3f}"),
                ],
            ),
        )

    def _log_document_message_received(
        self,
        update: Update,
        file_name: str | None,
        file_size: int | None,
    ) -> None:
        logger.info(
            format_markdown_event(
                log_events.DOCUMENT_MESSAGE_RECEIVED,
                [
                    ("Chat ID", self._get_chat_id(update)),
                    ("User ID", self._get_user_id(update)),
                    ("File Name", file_name or "(missing)"),
                    ("File Size", file_size or 0),
                ],
            ),
        )

    def _log_document_message_processed(
        self,
        started_at: float,
        reply_text: str,
    ) -> None:
        elapsed_seconds = monotonic() - started_at
        logger.info(
            format_markdown_event(
                log_events.DOCUMENT_MESSAGE_PROCESSED,
                [
                    ("Reply Length", len(reply_text)),
                    ("Elapsed Seconds", f"{elapsed_seconds:.3f}"),
                ],
            ),
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

    def _format_file_too_large_message(self) -> str:
        return FILE_TOO_LARGE_MESSAGE.format(
            max_file_size_mb=self._file_processing_service.max_file_size_megabytes,
        )

    def _format_role_message(self) -> str:
        return ROLE_MESSAGE.format(
            agent_role=self._message_service.get_current_agent_role(),
        )

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

    def _read_command_argument(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        args = getattr(context, "args", None)
        if not args:
            return ""
        return " ".join(args).strip()

    async def _download_document_content(self, document) -> bytes:
        try:
            telegram_file = await document.get_file()
            content = await telegram_file.download_as_bytearray()
        except Exception as exc:
            raise FileProcessingError("Telegram file download failed.") from exc
        return bytes(content)
