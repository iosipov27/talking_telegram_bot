from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram.ext import Application, ApplicationBuilder, MessageHandler, filters

from talking_telegram_bot.clients.ollama_client import OllamaClient
from talking_telegram_bot.config.settings import Settings, SettingsError, load_settings
from talking_telegram_bot.controllers.telegram_controller import TelegramMessageController
from talking_telegram_bot.services.message_service import MessageService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE_PATH = PROJECT_ROOT / "logs" / "bot.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5


def main() -> None:
    _configure_logging()
    try:
        settings = load_settings()
    except SettingsError:
        logging.exception("Failed to load application settings.")
        raise

    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    message_service = MessageService(ollama_client)
    controller = TelegramMessageController(message_service)
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
    application.add_handler(MessageHandler(filters.TEXT, controller.handle_text_message))
    return application


def _build_shutdown_callback(ollama_client: OllamaClient):
    async def shutdown_callback(application: Application) -> None:
        del application
        await ollama_client.close()

    return shutdown_callback


def _configure_logging(log_file_path: Path = LOG_FILE_PATH) -> None:
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        format=LOG_FORMAT,
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                log_file_path,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            ),
        ],
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
