# Talking Telegram Bot

A simple Telegram bot that sends every text message to a local Ollama LLM and replies with the generated answer.

The bot does not use a database. It does not store chat history. Each Telegram message is processed as a separate LLM request.

## What It Does

- Replies to text messages in Telegram.
- Sends each message to Ollama through `POST /api/chat`.
- Uses `stream: false` for LLM responses.
- Handles LLM and network errors with a safe Telegram reply.
- Runs in Telegram polling mode.
- Writes logs to the console and to `logs/bot.log`.
- Lets the user list and switch local Ollama models with `/models`.

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

## Select A Model

The default model is configured by `OLLAMA_MODEL` in `.env`.

While the bot is running, send this Telegram command:

```text
/models
```

The bot asks Ollama for locally available models and sends a list of buttons.
Tap a model button to make it the current model.

Model selection is kept only in process memory. If the bot restarts, it uses `OLLAMA_MODEL` from `.env` again.

## Logs

Logs are written to two places:

- console output while the bot is running;
- `logs/bot.log` for later error analysis.

The log directory is ignored by git.
Logs include safe event metadata: message received, reply sent, model list requested, model switched, text length, reply length, chat id, user id, and processing time.

Logs do not include Telegram bot tokens, `.env` values, user message text, or LLM reply text.

If the LLM is not available, the bot logs the processing error and replies in Telegram with:

```text
LLM is currently unavailable. Please try again later.
```

## Tests

Run unit tests:

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```
