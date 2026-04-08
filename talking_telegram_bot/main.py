from __future__ import annotations

import logging

from telegram.ext import Application, ApplicationBuilder, MessageHandler, filters

from talking_telegram_bot.clients.ollama_client import OllamaClient
from talking_telegram_bot.config.settings import Settings, SettingsError, load_settings
from talking_telegram_bot.controllers.telegram_controller import TelegramMessageController
from talking_telegram_bot.services.message_service import MessageService


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


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
