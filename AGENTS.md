# Agent Instructions

## Package Manager
- Use the project virtualenv and `pip`: `.venv/bin/pip install -r requirements.txt`

## File-Scoped Commands
| Task | Command |
|------|---------|
| Run bot | `.venv/bin/python -m talking_telegram_bot` |
| All tests | `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v` |
| One test module | `PYTHONPATH=. .venv/bin/python -m unittest tests.test_message_service -v` |

## Commit Attribution
- AI commits must include:
```text
Co-Authored-By: Codex <noreply@openai.com>
```

## Key Conventions
- Use `python-telegram-bot` for Telegram integration.
- Use `https://python-telegram-bot.org/` as the primary Telegram reference.
- Do not add a database or other persistent store unless explicitly requested.
- Never log Telegram bot tokens, API keys, `.env` values, or URLs that contain secrets.
- Write application logs to both the console and `logs/bot.log`.

## Architecture
- Keep the layered structure: Entry Point -> Controller -> Service -> Client -> Service -> Controller.
- Entry point owns bootstrap, logging setup, dependency wiring, and polling startup.
- Controllers own Telegram-specific input/output, command handling, callback handling, and Telegram file download.
- Services own validation, orchestration, runtime decisions, agent flow, and user-safe response shaping.
- Services may depend on other services and clients; services must not perform raw `httpx` calls directly.
- Clients own external communication, file-backed persistence, timeouts, and low-level exceptions.
- Models stay as pure data structures.

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

## Coding Style
- Prefer the smallest readable change that matches the existing code style.
- Keep functions focused, naming explicit, and nesting shallow.
- Do not refactor unrelated code while making a targeted change.
