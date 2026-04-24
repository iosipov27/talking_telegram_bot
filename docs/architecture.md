# Architecture

This document describes the architecture that is now wired in `main.py`, plus the legacy compatibility layer that still exists in the repository.

## Current Runtime

The active runtime is a single-process event-driven bot built on native Python primitives:

- `asyncio.Queue` inside the in-memory buses
- class-based command handlers
- class-based event subscribers
- one outbound Telegram adapter for replies, progress updates, and callback edits
- one workflow for the multi-step agent loop

## Current Bootstrap Flow

```text
talking_telegram_bot.__main__
  -> main.main()
  -> _configure_logging()
  -> load_settings()
  -> OllamaClient / TavilyClient
  -> InMemoryCommandBus / InMemoryEventBus
  -> runtime services
  -> command handlers
  -> event subscribers
  -> python-telegram-bot Application
```

`main.py` now wires the new event-driven path. The old `TelegramMessageController`, `MessageService`, and `AutonomousAgentService` are still present as a compatibility layer and remain covered by the existing tests, but they are no longer the runtime path used by the app bootstrap.

The active runtime now has a deterministic weather router in front of the agent plus two agent tools:
- pre-agent weather routing for weather questions without a date;
- `search_web` for general current information;
- `calculator` for deterministic math.

Conversation history and summaries are present but disabled by default. Set
`CONVERSATION_HISTORY_ENABLED=true` to wire `ConversationContextService`,
`ConversationSummaryService`, and `HistoryEventSubscriber` into the active runtime.

## Current Request Flows

### Text Message

```text
TelegramTextController
  -> InMemoryCommandBus.execute(ProcessTextMessage)
  -> ProcessTextMessageHandler
  -> WeatherQueryRouterService
  -> weather path: LocationNormalizationService -> WeatherService -> WeatherReplyFormatterService -> ReplyReady
  -> agent path: StartTelegramResponseSession -> AgentRunRequested -> AgentRunWorkflow
  -> ToolExecutionRequested / ProgressUpdated / ReplyReady
  -> TelegramOutboundController
```

### Document Message

```text
TelegramDocumentController
  -> Telegram file download
  -> InMemoryCommandBus.execute(ProcessDocumentMessage)
  -> ProcessDocumentMessageHandler
  -> FileProcessingService validation
  -> InMemoryEventBus.publish_and_wait(StartTelegramResponseSession)
  -> InMemoryEventBus.publish_and_wait(AgentRunRequested)
  -> AgentRunWorkflow
  -> ToolExecutionRequested / ProgressUpdated / ReplyReady
  -> TelegramOutboundController
```

### Tool Dispatch

```text
AgentRunWorkflow
  -> ToolExecutionRequested(action="search_web" | "calculator")
  -> SearchWebToolHandler | CalculatorToolHandler
  -> tool observation
  -> AgentRunWorkflow
```

### Model and Role Commands

```text
TelegramCommandController
  -> ListModels / ShowRole / UpdateRole
  -> command handlers
  -> ModelListReady or TextReplyRequested
  -> TelegramOutboundController
```

### Model Callback

```text
TelegramCallbackController
  -> SelectModel
  -> SelectModelHandler
  -> CallbackTextRequested
  -> TelegramOutboundController
```

## Current Class Map

### Bus Layer

| Module | Class | Responsibility | Direct dependencies |
|---|---|---|---|
| `talking_telegram_bot/bus/envelope.py` | `MessageEnvelope` | Wraps commands and events with message and correlation metadata | `uuid`, `datetime` |
| `talking_telegram_bot/bus/registry.py` | `HandlerRegistry` | Stores one command handler per command type and many subscribers per event type | stdlib collections |
| `talking_telegram_bot/bus/dead_letter.py` | `DeadLetterWriter` | Writes failed envelopes to `logs/dead_letter.jsonl` | filesystem, `asyncio.to_thread()` |
| `talking_telegram_bot/bus/command_bus.py` | `InMemoryCommandBus` | Queues commands, dispatches them to registered handlers, and can await completion | `asyncio.Queue`, `HandlerRegistry`, `DeadLetterWriter` |
| `talking_telegram_bot/bus/event_bus.py` | `InMemoryEventBus` | Queues events, fans them out to registered subscribers, and can await subscriber completion | `asyncio.Queue`, `HandlerRegistry`, `DeadLetterWriter` |

### Controllers

| Module | Class | Responsibility | Direct dependencies |
|---|---|---|---|
| `talking_telegram_bot/controllers/telegram_text_controller.py` | `TelegramTextController` | Converts Telegram text updates into `ProcessTextMessage` commands | `InMemoryCommandBus`, `InMemoryEventBus` |
| `talking_telegram_bot/controllers/telegram_document_controller.py` | `TelegramDocumentController` | Downloads Telegram documents and converts them into `ProcessDocumentMessage` commands | `InMemoryCommandBus`, `InMemoryEventBus` |
| `talking_telegram_bot/controllers/telegram_command_controller.py` | `TelegramCommandController` | Converts `/models` and `/role` into commands | `InMemoryCommandBus` |
| `talking_telegram_bot/controllers/telegram_callback_controller.py` | `TelegramCallbackController` | Converts model-selection callbacks into `SelectModel` commands | `InMemoryCommandBus` |
| `talking_telegram_bot/controllers/telegram_outbound_controller.py` | `TelegramOutboundController` | Handles outbound Telegram replies, callback edits, model keyboards, and progress session lifecycle | Telegram message/query objects |

### Command Handlers

| Module | Class | Responsibility | Direct dependencies |
|---|---|---|---|
| `talking_telegram_bot/handlers/process_text_message_handler.py` | `ProcessTextMessageHandler` | Normalizes inbound text, routes no-date weather questions before the agent, and otherwise triggers the agent workflow | `MessageInputService`, `PromptBuilderService`, `WeatherQueryRouterService`, `WeatherService`, `WeatherReplyFormatterService`, `InMemoryEventBus` |
| `talking_telegram_bot/handlers/process_document_message_handler.py` | `ProcessDocumentMessageHandler` | Validates documents, builds prompt text, starts a Telegram response session, and triggers the agent workflow | `FileProcessingService`, `PromptBuilderService`, `InMemoryEventBus` |
| `talking_telegram_bot/handlers/list_models_handler.py` | `ListModelsHandler` | Loads the active model list and emits `ModelListReady` | `ModelRuntimeService`, `InMemoryEventBus` |
| `talking_telegram_bot/handlers/show_role_handler.py` | `ShowRoleHandler` | Returns the current runtime role | `RoleRuntimeService`, `InMemoryEventBus` |
| `talking_telegram_bot/handlers/update_role_handler.py` | `UpdateRoleHandler` | Updates the runtime role and returns the selected role or current-role message | `RoleRuntimeService`, `InMemoryEventBus` |
| `talking_telegram_bot/handlers/select_model_handler.py` | `SelectModelHandler` | Parses callback payloads, switches the runtime model, and emits callback text updates | `ModelRuntimeService`, `InMemoryEventBus` |
| `talking_telegram_bot/handlers/search_web_tool_handler.py` | `SearchWebToolHandler` | Executes `search_web` tool requests and reports tool observations through a future | `SearchWebService`, `AgentResponseService`, `InMemoryEventBus` |
| `talking_telegram_bot/handlers/calculator_tool_handler.py` | `CalculatorToolHandler` | Executes `calculator` tool requests and reports tool observations through a future | `CalculatorService`, `AgentResponseService` |

### Workflow

| Module | Class | Responsibility | Direct dependencies |
|---|---|---|---|
| `talking_telegram_bot/workflows/agent_run_workflow.py` | `AgentRunWorkflow` | Owns the multi-step LLM loop, emits progress updates, requests tools, and emits the final reply or safe error | `AgentExecutionService`, `AgentResponseService`, `ConversationLockService`, `InMemoryEventBus` |

### Runtime Services

| Module | Class | Responsibility | Direct dependencies |
|---|---|---|---|
| `talking_telegram_bot/services/message_input_service.py` | `MessageInputService` | Normalizes raw user text and rejects empty input | none |
| `talking_telegram_bot/services/prompt_builder_service.py` | `PromptBuilderService` | Builds the system prompt from the current runtime role | `RoleRuntimeService` |
| `talking_telegram_bot/services/agent_execution_service.py` | `AgentExecutionService` | Executes one LLM step against Ollama | `OllamaClient`, `AgentRequestBuilderService` |
| `talking_telegram_bot/services/agent_response_service.py` | `AgentResponseService` | Parses agent JSON, final answers, and tool calls | none |
| `talking_telegram_bot/services/conversation_lock_service.py` | `ConversationLockService` | Ensures one active agent run per user at a time | `asyncio.Lock` |
| `talking_telegram_bot/services/role_runtime_service.py` | `RoleRuntimeService` | Stores and validates the in-memory runtime role | none |
| `talking_telegram_bot/services/model_runtime_service.py` | `ModelRuntimeService` | Stores and switches the in-memory active model | `OllamaClient` |
| `talking_telegram_bot/services/file_processing_service.py` | `FileProcessingService` | Validates file type and size and turns bytes into document prompt text | none |
| `talking_telegram_bot/services/conversation_context_service.py` | `ConversationContextService` | Optionally reads file-backed chat history and summaries and builds agent context messages | `ChatHistoryClient` |
| `talking_telegram_bot/services/conversation_summary_service.py` | `ConversationSummaryService` | Optionally updates file-backed conversation summaries after enough complete request and response pairs | `ConversationContextService`, `OllamaClient` |
| `talking_telegram_bot/services/location_normalization_service.py` | `LocationNormalizationService` | Normalizes user-entered locations, resolves English place names, and produces stable lookup queries for weather requests | `NominatimClient` |
| `talking_telegram_bot/services/weather_query_router_service.py` | `WeatherQueryRouterService` | Detects weather questions without a date and extracts a location hint for deterministic routing | `re` |
| `talking_telegram_bot/services/weather_reply_formatter_service.py` | `WeatherReplyFormatterService` | Converts a `WeatherResponse` into a Telegram-facing reply | none |
| `talking_telegram_bot/services/weather_service.py` | `WeatherService` | Validates the requested location, normalizes it for weather lookup, and maps client failures to service-level errors | `WttrClient`, `LocationNormalizationService` |

### Clients

| Module | Class | Responsibility | Direct dependencies |
|---|---|---|---|
| `talking_telegram_bot/clients/ollama_client.py` | `OllamaClient` | Talks to Ollama over HTTP and maintains the runtime model name | `httpx.AsyncClient` |
| `talking_telegram_bot/clients/tavily_client.py` | `TavilyClient` | Talks to Tavily over HTTP and converts payloads into search models | `httpx.AsyncClient` |
| `talking_telegram_bot/clients/nominatim_client.py` | `NominatimClient` | Talks to Nominatim over HTTP and resolves user-entered places into English names and lookup coordinates | `httpx.AsyncClient` |
| `talking_telegram_bot/clients/wttr_client.py` | `WttrClient` | Talks to `wttr.in` over HTTP and converts JSON payloads into weather models | `httpx.AsyncClient` |
| `talking_telegram_bot/clients/chat_history_client.py` | `ChatHistoryClient` | Reads and writes file-backed per-user history and summaries | filesystem, `asyncio.to_thread()` |

### Message Contracts

| Module | Class | Responsibility |
|---|---|---|
| `talking_telegram_bot/messages/commands.py` | `ProcessTextMessage` | Start text-message processing |
| `talking_telegram_bot/messages/commands.py` | `ProcessDocumentMessage` | Start document-message processing |
| `talking_telegram_bot/messages/commands.py` | `ListModels` | Load current and available models |
| `talking_telegram_bot/messages/commands.py` | `ShowRole` | Return the current agent role |
| `talking_telegram_bot/messages/commands.py` | `UpdateRole` | Update the current agent role |
| `talking_telegram_bot/messages/commands.py` | `SelectModel` | Switch the active model from callback data |
| `talking_telegram_bot/messages/events.py` | `StartTelegramResponseSession` | Start a reply/progress session for a Telegram message |
| `talking_telegram_bot/messages/events.py` | `ProgressUpdated` | Update the progress message text |
| `talking_telegram_bot/messages/events.py` | `ReplyReady` | Deliver the final reply for the current session |
| `talking_telegram_bot/messages/events.py` | `UserFacingErrorRaised` | Deliver a safe Telegram-facing error, with optional fallback message |
| `talking_telegram_bot/messages/events.py` | `TextReplyRequested` | Send a direct Telegram reply without a progress session |
| `talking_telegram_bot/messages/events.py` | `CallbackTextRequested` | Edit callback query text |
| `talking_telegram_bot/messages/events.py` | `ModelListReady` | Deliver model list payload for keyboard rendering |
| `talking_telegram_bot/messages/events.py` | `AgentRunRequested` | Trigger the multi-step agent workflow |
| `talking_telegram_bot/messages/events.py` | `ToolExecutionRequested` | Request a tool observation from one of the tool subscribers |

## Current Ownership Rules

- Inbound controllers translate Telegram updates into commands.
- Command handlers own one use-case entry each.
- No-date weather questions are handled deterministically before the LLM loop starts.
- `AgentRunWorkflow` owns the agent loop and nothing else.
- Outbound Telegram IO is centralized in `TelegramOutboundController`.
- Services stay transport-agnostic.
- Clients own raw IO and low-level failures.
- The old synchronous stack stays in the tree as a compatibility layer until a later cleanup removes it.

## Legacy Compatibility Layer

These classes still exist and still have tests, but they are no longer the `main.py` runtime path:

- `talking_telegram_bot/controllers/telegram_controller.py`
- `talking_telegram_bot/services/message_service.py`
- `talking_telegram_bot/services/autonomous_agent_service.py`
- `talking_telegram_bot/services/model_service.py`
- `talking_telegram_bot/services/agent_tool_service.py`

They can be removed in a later cleanup once every remaining caller and test target has been moved to the new command and event path.

## Next Migration Steps

1. Move or rewrite the legacy controller and service tests so they target the new runtime path directly.
2. Remove the old synchronous compatibility layer once the new path is the only supported path.
