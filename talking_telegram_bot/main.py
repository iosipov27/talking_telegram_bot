from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from talking_telegram_bot.clients.chat_history_client import ChatHistoryClient
from talking_telegram_bot.clients.ollama_client import OllamaClient
from talking_telegram_bot.config.settings import Settings, SettingsError, load_settings
from talking_telegram_bot.constants.log_events import SETTINGS_LOAD_FAILED
from talking_telegram_bot.constants.logging_settings import (
    LOG_BACKUP_COUNT,
    LOG_DATE_FORMAT,
    LOG_FILE_PATH,
    LOG_MAX_BYTES,
)
from talking_telegram_bot.constants.telegram import (
    MODEL_CALLBACK_PREFIX,
    MODELS_COMMAND,
    ROLE_COMMAND,
)
from talking_telegram_bot.controllers.telegram_controller import (
    TelegramMessageController,
)
from talking_telegram_bot.logging_utils import MarkdownLogFormatter
from talking_telegram_bot.services.message_service import MessageService
from talking_telegram_bot.services.model_service import ModelService


def main() -> None:
    _configure_logging()
    try:
        settings = load_settings()
    except SettingsError:
        logging.exception(SETTINGS_LOAD_FAILED)
        raise

    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    chat_history_client = ChatHistoryClient()
    message_service = MessageService(
        ollama_client,
        chat_history_client,
        settings.ollama_agent_role,
    )
    model_service = ModelService(ollama_client)
    controller = TelegramMessageController(message_service, model_service)
    application = _build_application(settings, controller, ollama_client)
    application.run_polling()


def _build_application(
    settings: Settings,
    controller: TelegramMessageController,
    ollama_client: OllamaClient,
) -> Application:
    builder = ApplicationBuilder()
    builder = builder.token(settings.telegram_bot_token)
    builder = builder.concurrent_updates(settings.telegram_concurrent_updates)
    builder = builder.post_shutdown(_build_shutdown_callback(ollama_client))
    application = builder.build()
    application.add_handler(
        CommandHandler(MODELS_COMMAND, controller.handle_models_command),
    )
    application.add_handler(
        CommandHandler(ROLE_COMMAND, controller.handle_role_command),
    )
    application.add_handler(
        CallbackQueryHandler(
            controller.handle_model_selection,
            pattern=f"^{MODEL_CALLBACK_PREFIX}",
        ),
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            controller.handle_text_message,
        ),
    )
    return application


def _build_shutdown_callback(ollama_client: OllamaClient):
    async def shutdown_callback(application: Application) -> None:
        del application
        await ollama_client.close()

    return shutdown_callback


def _configure_logging(log_file_path: Path = LOG_FILE_PATH) -> None:
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        MarkdownLogFormatter(
            use_colors=True,
            datefmt=LOG_DATE_FORMAT,
        ),
    )
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        MarkdownLogFormatter(
            datefmt=LOG_DATE_FORMAT,
        ),
    )
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
