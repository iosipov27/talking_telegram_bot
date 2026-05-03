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

from talking_telegram_bot.bus.command_bus import InMemoryCommandBus
from talking_telegram_bot.bus.dead_letter import DeadLetterWriter
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.clients.chat_history_client import ChatHistoryClient
from talking_telegram_bot.clients.nominatim_client import NominatimClient
from talking_telegram_bot.clients.ollama_client import OllamaClient
from talking_telegram_bot.clients.tavily_client import TavilyClient
from talking_telegram_bot.clients.wttr_client import WttrClient
from talking_telegram_bot.config.settings import Settings, SettingsError, load_settings
from talking_telegram_bot.constants.log_events import (
    SENTRY_CONFIGURED,
    SENTRY_CONFIGURATION_FAILED,
    SETTINGS_LOAD_FAILED,
)
from talking_telegram_bot.constants.logging_settings import (
    LOG_BACKUP_COUNT,
    LOG_FILE_PATH,
    LOG_MAX_BYTES,
)
from talking_telegram_bot.constants.telegram import (
    MODEL_CALLBACK_PREFIX,
    MODELS_COMMAND,
    ROLE_COMMAND,
)
from talking_telegram_bot.controllers.telegram_callback_controller import (
    TelegramCallbackController,
)
from talking_telegram_bot.controllers.telegram_command_controller import (
    TelegramCommandController,
)
from talking_telegram_bot.controllers.telegram_document_controller import (
    TelegramDocumentController,
)
from talking_telegram_bot.controllers.telegram_outbound_controller import (
    TelegramOutboundController,
)
from talking_telegram_bot.controllers.telegram_text_controller import (
    TelegramTextController,
)
from talking_telegram_bot.handlers.calculator_tool_handler import CalculatorToolHandler
from talking_telegram_bot.handlers.history_event_subscriber import HistoryEventSubscriber
from talking_telegram_bot.handlers.list_models_handler import ListModelsHandler
from talking_telegram_bot.handlers.process_document_message_handler import (
    ProcessDocumentMessageHandler,
)
from talking_telegram_bot.handlers.process_text_message_handler import (
    ProcessTextMessageHandler,
)
from talking_telegram_bot.handlers.search_web_tool_handler import SearchWebToolHandler
from talking_telegram_bot.handlers.select_model_handler import SelectModelHandler
from talking_telegram_bot.handlers.show_role_handler import ShowRoleHandler
from talking_telegram_bot.handlers.update_role_handler import UpdateRoleHandler
from talking_telegram_bot.logging_utils import (
    JsonLogFormatter,
    MarkdownLogFormatter,
    log_event,
)
from talking_telegram_bot.messages.commands import (
    ListModels,
    ProcessDocumentMessage,
    ProcessTextMessage,
    SelectModel,
    ShowRole,
    UpdateRole,
)
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    CallbackTextRequested,
    MessageReceived,
    ModelListReady,
    ProgressUpdated,
    ReplyReady,
    ResponseGenerated,
    StartTelegramResponseSession,
    TextReplyRequested,
    ToolExecutionRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.services.agent_execution_service import AgentExecutionService
from talking_telegram_bot.services.agent_request_builder_service import (
    AgentRequestBuilderService,
)
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.calculator_service import CalculatorService
from talking_telegram_bot.services.conversation_context_service import (
    ConversationContextService,
)
from talking_telegram_bot.services.conversation_lock_service import (
    ConversationLockService,
)
from talking_telegram_bot.services.conversation_summary_service import (
    ConversationSummaryService,
)
from talking_telegram_bot.services.file_processing_service import FileProcessingService
from talking_telegram_bot.services.location_normalization_service import (
    LocationNormalizationService,
)
from talking_telegram_bot.services.message_input_service import MessageInputService
from talking_telegram_bot.services.model_runtime_service import ModelRuntimeService
from talking_telegram_bot.services.search_web_service import SearchWebService
from talking_telegram_bot.services.prompt_builder_service import PromptBuilderService
from talking_telegram_bot.services.role_runtime_service import RoleRuntimeService
from talking_telegram_bot.services.weather_service import WeatherService
from talking_telegram_bot.services.weather_query_router_service import (
    WeatherQueryRouterService,
)
from talking_telegram_bot.services.weather_reply_formatter_service import (
    WeatherReplyFormatterService,
)
from talking_telegram_bot.sentry_utils import (
    SentryConfigurationError,
    configure_sentry,
)
from talking_telegram_bot.workflows.agent_run_workflow import AgentRunWorkflow

logger = logging.getLogger(__name__)


def main() -> None:
    _configure_logging()
    try:
        settings = load_settings()
    except SettingsError:
        log_event(
            logger,
            logging.ERROR,
            SETTINGS_LOAD_FAILED,
            exc_info=True,
        )
        raise
    try:
        sentry_enabled = configure_sentry(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
        )
    except SentryConfigurationError:
        log_event(
            logger,
            logging.ERROR,
            SENTRY_CONFIGURATION_FAILED,
            exc_info=True,
        )
        raise
    if sentry_enabled:
        log_event(
            logger,
            logging.INFO,
            SENTRY_CONFIGURED,
            environment=settings.sentry_environment,
        )

    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    tavily_client = TavilyClient(
        api_key=settings.tavily_api_key,
        base_url=settings.tavily_base_url,
        timeout_seconds=settings.tavily_timeout_seconds,
    )
    nominatim_client = NominatimClient(
        base_url=settings.nominatim_base_url,
        timeout_seconds=settings.nominatim_timeout_seconds,
        user_agent=settings.nominatim_user_agent,
    )
    wttr_client = WttrClient(
        base_url=settings.wttr_base_url,
        timeout_seconds=settings.wttr_timeout_seconds,
    )
    dead_letter_writer = DeadLetterWriter()
    command_bus = InMemoryCommandBus(
        dead_letter_writer=dead_letter_writer,
        worker_count=settings.telegram_concurrent_updates,
    )
    event_bus = InMemoryEventBus(
        dead_letter_writer=dead_letter_writer,
        worker_count=max(4, settings.telegram_concurrent_updates),
    )
    search_web_service = SearchWebService(tavily_client)
    location_normalization_service = LocationNormalizationService(nominatim_client)
    weather_service = WeatherService(wttr_client, location_normalization_service)
    calculator_service = CalculatorService()
    role_runtime_service = RoleRuntimeService(settings.ollama_agent_role)
    model_runtime_service = ModelRuntimeService(ollama_client)
    message_input_service = MessageInputService()
    prompt_builder_service = PromptBuilderService(role_runtime_service)
    weather_query_router_service = WeatherQueryRouterService()
    weather_reply_formatter_service = WeatherReplyFormatterService()
    agent_execution_service = AgentExecutionService(
        ollama_client,
        AgentRequestBuilderService(),
    )
    response_service = AgentResponseService()
    file_processing_service = FileProcessingService()
    conversation_lock_service = ConversationLockService()
    conversation_context_service = None
    history_event_subscriber = None
    if settings.conversation_history_enabled:
        conversation_context_service = ConversationContextService(ChatHistoryClient())
        conversation_summary_service = ConversationSummaryService(
            conversation_context_service,
            ollama_client,
        )
        history_event_subscriber = HistoryEventSubscriber(
            conversation_context_service,
            conversation_summary_service,
        )
    outbound_controller = TelegramOutboundController()
    text_controller = TelegramTextController(command_bus, event_bus)
    document_controller = TelegramDocumentController(command_bus, event_bus)
    command_controller = TelegramCommandController(command_bus)
    callback_controller = TelegramCallbackController(command_bus)

    command_bus.register_handler(
        ProcessTextMessage,
        ProcessTextMessageHandler(
            message_input_service,
            prompt_builder_service,
            event_bus,
            weather_query_router_service,
            weather_service,
            weather_reply_formatter_service,
        ),
    )
    command_bus.register_handler(
        ProcessDocumentMessage,
        ProcessDocumentMessageHandler(
            file_processing_service,
            prompt_builder_service,
            event_bus,
        ),
    )
    command_bus.register_handler(
        ListModels,
        ListModelsHandler(model_runtime_service, event_bus),
    )
    command_bus.register_handler(
        ShowRole,
        ShowRoleHandler(role_runtime_service, event_bus),
    )
    command_bus.register_handler(
        UpdateRole,
        UpdateRoleHandler(role_runtime_service, event_bus),
    )
    command_bus.register_handler(
        SelectModel,
        SelectModelHandler(model_runtime_service, event_bus),
    )

    event_bus.subscribe(
        AgentRunRequested,
        AgentRunWorkflow(
            agent_execution_service,
            response_service,
            event_bus,
            conversation_lock_service,
            conversation_context_service,
        ),
    )
    event_bus.subscribe(
        ToolExecutionRequested,
        SearchWebToolHandler(response_service, search_web_service, event_bus),
    )
    event_bus.subscribe(
        ToolExecutionRequested,
        CalculatorToolHandler(response_service, calculator_service),
    )
    if history_event_subscriber is not None:
        event_bus.subscribe(MessageReceived, history_event_subscriber)
        event_bus.subscribe(ResponseGenerated, history_event_subscriber)
    for event_type in (
        StartTelegramResponseSession,
        ProgressUpdated,
        ReplyReady,
        UserFacingErrorRaised,
        TextReplyRequested,
        CallbackTextRequested,
        ModelListReady,
    ):
        event_bus.subscribe(event_type, outbound_controller)

    application = _build_application(
        settings,
        text_controller,
        document_controller,
        command_controller,
        callback_controller,
        ollama_client,
        tavily_client,
        nominatim_client,
        wttr_client,
        command_bus,
        event_bus,
    )
    application.run_polling()


def _build_application(
    settings: Settings,
    text_controller: TelegramTextController,
    document_controller: TelegramDocumentController,
    command_controller: TelegramCommandController,
    callback_controller: TelegramCallbackController,
    ollama_client: OllamaClient,
    tavily_client: TavilyClient,
    nominatim_client: NominatimClient,
    wttr_client: WttrClient,
    command_bus: InMemoryCommandBus,
    event_bus: InMemoryEventBus,
) -> Application:
    builder = ApplicationBuilder()
    builder = builder.token(settings.telegram_bot_token)
    builder = builder.concurrent_updates(settings.telegram_concurrent_updates)
    builder = builder.post_init(_build_startup_callback(command_bus, event_bus))
    builder = builder.post_shutdown(
        _build_shutdown_callback(
            ollama_client,
            tavily_client,
            nominatim_client,
            wttr_client,
            command_bus,
            event_bus,
        ),
    )
    application = builder.build()
    application.add_handler(
        CommandHandler(MODELS_COMMAND, command_controller.handle_models_command),
    )
    application.add_handler(
        CommandHandler(ROLE_COMMAND, command_controller.handle_role_command),
    )
    application.add_handler(
        CallbackQueryHandler(
            callback_controller.handle_model_selection,
            pattern=f"^{MODEL_CALLBACK_PREFIX}",
        ),
    )
    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            document_controller.handle_document_message,
        ),
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_controller.handle_text_message,
        ),
    )
    return application


def _build_startup_callback(
    command_bus: InMemoryCommandBus,
    event_bus: InMemoryEventBus,
):
    async def startup_callback(application: Application) -> None:
        del application
        await command_bus.start()
        await event_bus.start()

    return startup_callback


def _build_shutdown_callback(
    ollama_client: OllamaClient,
    tavily_client: TavilyClient,
    nominatim_client: NominatimClient,
    wttr_client: WttrClient,
    command_bus: InMemoryCommandBus,
    event_bus: InMemoryEventBus,
):
    async def shutdown_callback(application: Application) -> None:
        del application
        await command_bus.stop()
        await event_bus.stop()
        await ollama_client.close()
        await tavily_client.close()
        await nominatim_client.close()
        await wttr_client.close()

    return shutdown_callback


def _configure_logging(log_file_path: Path = LOG_FILE_PATH) -> None:
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(MarkdownLogFormatter(use_colors=True))
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
