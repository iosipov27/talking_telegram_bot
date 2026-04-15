# Talking Telegram Bot

A simple Telegram bot that sends every text message to a local Ollama LLM and replies with the generated answer.

The bot does not use a database. It stores per-user chat history as JSON files in `logs`. Each Telegram message is processed as a separate LLM request with that user's saved history.

## What It Does

- Replies to text messages in Telegram.
- Sends each message and that user's saved history to Ollama through `POST /api/chat`.
- Uses `stream: false` for LLM responses.
- Handles LLM and network errors with a safe Telegram reply.
- Runs in Telegram polling mode.
- Writes logs to the console and to `logs/bot.log`.
- Writes a summary and recent request and LLM response pairs to per-user JSON files in `logs`.
- Summarizes saved history after 5 pairs and sends the summary with new requests.
- Keeps summary settings in `talking_telegram_bot/constants/summary_settings.py`.
- Lets the user list and switch local Ollama models with `/models`.
- Sends a system prompt with each user request so the model keeps the selected role.
- Lets the user change the runtime agent role with `/role`.

## Project Structure

- `talking_telegram_bot/main.py` starts the application and wires dependencies.
- `talking_telegram_bot/controllers/` receives Telegram updates and sends Telegram replies.
- `talking_telegram_bot/services/` contains message processing logic.
- `talking_telegram_bot/clients/` communicates with Ollama.
- `talking_telegram_bot/config/` reads environment settings.
- `talking_telegram_bot/models/` contains simple data objects.
- `tests/` contains unit tests.

## Setup

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Fill the local `.env` file:

```bash
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:0.8b
OLLAMA_AGENT_ROLE=опытный программист
OLLAMA_TIMEOUT_SECONDS=60
```

The `.env` file is ignored by git. Do not commit real tokens.

## Run

Start Ollama and make sure the configured model is available.

Then run the bot:

```bash
.venv/bin/python -m talking_telegram_bot
```

Open Telegram, send a text message to your bot, and wait for the reply.

Each user request includes a system prompt in the LLM context:

```text
Ты опытный программист и отвечаешь кратко и по делу.
```

The default role comes from `OLLAMA_AGENT_ROLE` in `.env`.

## Select A Model

The default model is configured by `OLLAMA_MODEL` in `.env`.

While the bot is running, send this Telegram command:

```text
/models
```

The bot asks Ollama for locally available models and sends a list of buttons.
Tap a model button to make it the current model.

Model selection is kept only in process memory. If the bot restarts, it uses `OLLAMA_MODEL` from `.env` again.

## Set Agent Role

While the bot is running, send this Telegram command:

```text
/role senior python developer
```

The bot updates the runtime role and includes it in the system prompt for following requests.
If the bot restarts, it uses `OLLAMA_AGENT_ROLE` from `.env` again.

## Logs

Logs are written to two places:

- console output while the bot is running;
- `logs/bot.log` for later error analysis.
- `logs/chat_history_<user_id>.json` for per-user request and LLM response history, plus the latest summary.

The log directory is ignored by git.
Console and `logs/bot.log` use markdown-style tables for log entries.
Console log headers are colorized by level for easier scanning.
Application logs now include full user messages, full Ollama request context, full Ollama responses, and generated summaries.
Application logs still do not include Telegram bot tokens or other secret `.env` values.

If the LLM is not available, the bot logs the processing error and replies in Telegram with:

```text
LLM is currently unavailable. Please try again later.
```

## Tests

Run unit tests:

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```
