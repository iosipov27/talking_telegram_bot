# Agent Instructions

This file is the entry point for agent work in this repository.

Read the split documents before changing the code:
- `docs/development.md` for package management, commands, commit attribution, and coding style.
- `docs/runtime.md` for Telegram, Ollama, logging, persistence, and error-handling rules.
- `docs/architecture.md` for the current class map, the current runtime flow, and the target event-driven split.

## Fast Rules
- Use the project virtualenv and `pip`: `.venv/bin/pip install -r requirements.txt`
- Keep the smallest readable change that matches the existing style.
- Do not add a database or any other persistent store unless explicitly requested.
- Do not log Telegram bot tokens, API keys, `.env` values, or URLs that contain secrets.
- Write application logs to both the console and `logs/bot.log`.
- Services must not perform raw `httpx` calls directly; external communication belongs in clients.

## File-Scoped Commands
| Task | Command |
|------|---------|
| Run bot | `.venv/bin/python -m talking_telegram_bot` |
| All tests | `PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v` |
| One test module | `PYTHONPATH=. .venv/bin/python -m unittest tests.test_message_service -v` |
