from __future__ import annotations

import logging
from dataclasses import dataclass
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
    UserFacingErrorRaised,
)
from talking_telegram_bot.services.agent_execution_service import AgentExecutionService
from talking_telegram_bot.services.agent_request_builder_service import (
    AgentRequestBuilderService,
)
from talking_telegram_bot.services.agent_request_orchestrator_service import (
    AgentRequestOrchestratorService,
)
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.agent_tool_dispatcher_service import (
    AgentToolDispatcherService,
)
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


@dataclass(frozen=True, slots=True)
class _RuntimeClients:
    ollama: OllamaClient
    tavily: TavilyClient
    nominatim: NominatimClient
    wttr: WttrClient


@dataclass(frozen=True, slots=True)
class _RuntimeBuses:
    command: InMemoryCommandBus
    event: InMemoryEventBus


@dataclass(frozen=True, slots=True)
class _RuntimeServices:
    message_input: MessageInputService
    agent_request_orchestrator: AgentRequestOrchestratorService
    weather_query_router: WeatherQueryRouterService
    weather: WeatherService
    weather_reply_formatter: WeatherReplyFormatterService
    file_processing: FileProcessingService
    model_runtime: ModelRuntimeService
    role_runtime: RoleRuntimeService
    agent_execution: AgentExecutionService
    agent_response: AgentResponseService
    agent_tool_dispatcher: AgentToolDispatcherService
    conversation_lock: ConversationLockService
    conversation_context: ConversationContextService | None
    history_event_subscriber: HistoryEventSubscriber | None


@dataclass(frozen=True, slots=True)
class _RuntimeControllers:
    text: TelegramTextController
    document: TelegramDocumentController
    command: TelegramCommandController
    callback: TelegramCallbackController
    outbound: TelegramOutboundController


def main() -> None:
    _configure_logging()
    settings = _load_runtime_settings()
    _configure_sentry(settings)

    clients = _build_clients(settings)
    buses = _build_buses(settings)
    services = _build_services(settings, clients, buses)
    controllers = _build_controllers(buses)

    _register_command_handlers(buses, services)
    _register_event_subscribers(buses, services, controllers)

    application = _build_application(settings, controllers, clients, buses)
    application.run_polling()


def _load_runtime_settings() -> Settings:
    try:
        return load_settings()
    except SettingsError:
        log_event(
            logger,
            logging.ERROR,
            SETTINGS_LOAD_FAILED,
            exc_info=True,
        )
        raise


def _configure_sentry(settings: Settings) -> None:
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


def _build_clients(settings: Settings) -> _RuntimeClients:
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
    return _RuntimeClients(
        ollama=ollama_client,
        tavily=tavily_client,
        nominatim=nominatim_client,
        wttr=wttr_client,
    )


def _build_buses(settings: Settings) -> _RuntimeBuses:
    dead_letter_writer = DeadLetterWriter()
    command_bus = InMemoryCommandBus(
        dead_letter_writer=dead_letter_writer,
        worker_count=settings.telegram_concurrent_updates,
    )
    event_bus = InMemoryEventBus(
        dead_letter_writer=dead_letter_writer,
        worker_count=max(4, settings.telegram_concurrent_updates),
    )
    return _RuntimeBuses(command=command_bus, event=event_bus)


def _build_services(
    settings: Settings,
    clients: _RuntimeClients,
    buses: _RuntimeBuses,
) -> _RuntimeServices:
    search_web_service = SearchWebService(clients.tavily)
    location_normalization_service = LocationNormalizationService(clients.nominatim)
    weather_service = WeatherService(clients.wttr, location_normalization_service)
    calculator_service = CalculatorService()
    role_runtime_service = RoleRuntimeService(settings.ollama_agent_role)
    model_runtime_service = ModelRuntimeService(clients.ollama)
    message_input_service = MessageInputService()
    prompt_builder_service = PromptBuilderService(role_runtime_service)
    agent_request_orchestrator_service = AgentRequestOrchestratorService(
        prompt_builder_service,
        buses.event,
    )
    weather_query_router_service = WeatherQueryRouterService()
    weather_reply_formatter_service = WeatherReplyFormatterService()
    agent_execution_service = AgentExecutionService(
        clients.ollama,
        AgentRequestBuilderService(),
    )
    response_service = AgentResponseService()
    file_processing_service = FileProcessingService()
    conversation_lock_service = ConversationLockService()
    search_web_tool_handler = SearchWebToolHandler(
        response_service,
        search_web_service,
        buses.event,
    )
    calculator_tool_handler = CalculatorToolHandler(
        response_service,
        calculator_service,
    )
    tool_dispatcher_service = AgentToolDispatcherService(
        [search_web_tool_handler, calculator_tool_handler],
    )
    conversation_context_service = None
    history_event_subscriber = None
    if settings.conversation_history_enabled:
        conversation_context_service = ConversationContextService(ChatHistoryClient())
        conversation_summary_service = ConversationSummaryService(
            conversation_context_service,
            clients.ollama,
        )
        history_event_subscriber = HistoryEventSubscriber(
            conversation_context_service,
            conversation_summary_service,
        )
    return _RuntimeServices(
        message_input=message_input_service,
        agent_request_orchestrator=agent_request_orchestrator_service,
        weather_query_router=weather_query_router_service,
        weather=weather_service,
        weather_reply_formatter=weather_reply_formatter_service,
        file_processing=file_processing_service,
        model_runtime=model_runtime_service,
        role_runtime=role_runtime_service,
        agent_execution=agent_execution_service,
        agent_response=response_service,
        agent_tool_dispatcher=tool_dispatcher_service,
        conversation_lock=conversation_lock_service,
        conversation_context=conversation_context_service,
        history_event_subscriber=history_event_subscriber,
    )


def _build_controllers(buses: _RuntimeBuses) -> _RuntimeControllers:
    outbound_controller = TelegramOutboundController()
    text_controller = TelegramTextController(buses.command, buses.event)
    document_controller = TelegramDocumentController(buses.command, buses.event)
    command_controller = TelegramCommandController(buses.command)
    callback_controller = TelegramCallbackController(buses.command)
    return _RuntimeControllers(
        text=text_controller,
        document=document_controller,
        command=command_controller,
        callback=callback_controller,
        outbound=outbound_controller,
    )


def _register_command_handlers(
    buses: _RuntimeBuses,
    services: _RuntimeServices,
) -> None:
    buses.command.register_handler(
        ProcessTextMessage,
        ProcessTextMessageHandler(
            services.message_input,
            services.agent_request_orchestrator,
            buses.event,
            services.weather_query_router,
            services.weather,
            services.weather_reply_formatter,
        ),
    )
    buses.command.register_handler(
        ProcessDocumentMessage,
        ProcessDocumentMessageHandler(
            services.file_processing,
            services.agent_request_orchestrator,
            buses.event,
        ),
    )
    buses.command.register_handler(
        ListModels,
        ListModelsHandler(services.model_runtime, buses.event),
    )
    buses.command.register_handler(
        ShowRole,
        ShowRoleHandler(services.role_runtime, buses.event),
    )
    buses.command.register_handler(
        UpdateRole,
        UpdateRoleHandler(services.role_runtime, buses.event),
    )
    buses.command.register_handler(
        SelectModel,
        SelectModelHandler(services.model_runtime, buses.event),
    )


def _register_event_subscribers(
    buses: _RuntimeBuses,
    services: _RuntimeServices,
    controllers: _RuntimeControllers,
) -> None:
    buses.event.subscribe(
        AgentRunRequested,
        AgentRunWorkflow(
            services.agent_execution,
            services.agent_response,
            services.agent_tool_dispatcher,
            buses.event,
            services.conversation_lock,
            services.conversation_context,
        ),
    )
    if services.history_event_subscriber is not None:
        buses.event.subscribe(MessageReceived, services.history_event_subscriber)
        buses.event.subscribe(ResponseGenerated, services.history_event_subscriber)
    for event_type in (
        StartTelegramResponseSession,
        ProgressUpdated,
        ReplyReady,
        UserFacingErrorRaised,
        TextReplyRequested,
        CallbackTextRequested,
        ModelListReady,
    ):
        buses.event.subscribe(event_type, controllers.outbound)


def _build_application(
    settings: Settings,
    controllers: _RuntimeControllers,
    clients: _RuntimeClients,
    buses: _RuntimeBuses,
) -> Application:
    builder = ApplicationBuilder()
    builder = builder.token(settings.telegram_bot_token)
    builder = builder.concurrent_updates(settings.telegram_concurrent_updates)
    builder = builder.post_init(_build_startup_callback(buses.command, buses.event))
    builder = builder.post_shutdown(
        _build_shutdown_callback(
            clients.ollama,
            clients.tavily,
            clients.nominatim,
            clients.wttr,
            buses.command,
            buses.event,
        ),
    )
    application = builder.build()
    application.add_handler(
        CommandHandler(MODELS_COMMAND, controllers.command.handle_models_command),
    )
    application.add_handler(
        CommandHandler(ROLE_COMMAND, controllers.command.handle_role_command),
    )
    application.add_handler(
        CallbackQueryHandler(
            controllers.callback.handle_model_selection,
            pattern=f"^{MODEL_CALLBACK_PREFIX}",
        ),
    )
    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            controllers.document.handle_document_message,
        ),
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            controllers.text.handle_text_message,
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
