# Runtime Rules

## Logging
- Write application logs to both the console and `logs/bot.log`.
- Never log Telegram bot tokens, API keys, `.env` values, or URLs that contain secrets.

## Telegram and LLM Behavior
- Telegram runs in polling mode.
- Keep one regular text handler; explicit command and callback handlers are allowed for bot controls.
- Ignore non-text input except supported document handling.
- Ollama chat requests must use `POST /api/chat`, `"stream": false`, and a timeout.
- `/models` must list Ollama models and switch the runtime model until process restart.
- `/role` may update the runtime agent role until process restart.
- Each incoming Telegram message is processed as a new LLM request. Stored chat history and summaries may be used as LLM context when the service flow enables them.

## Persistence and State
- File-based chat history and summaries in `logs/` are allowed.
- No database unless the user explicitly asks for it.
- In-memory runtime state is allowed for the current Ollama model and current agent role.

## Error Handling
- Clients raise technical exceptions.
- Services convert them to domain errors.
- Controllers return safe Telegram-facing messages.
- Treat timeout, empty LLM output, invalid LLM payloads, and overlong blocking generation as service-level failures.
- Do not silently retry inside clients.
