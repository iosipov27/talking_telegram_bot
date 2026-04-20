# Development Guide

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

## References
- Use `python-telegram-bot` for Telegram integration.
- Use `https://python-telegram-bot.org/` as the primary Telegram reference.

## Coding Style
- Prefer the smallest readable change that matches the existing code style.
- Keep functions focused, naming explicit, and nesting shallow.
- Do not refactor unrelated code while making a targeted change.
- Match the existing module ownership: controller logic stays Telegram-specific, service logic stays transport-agnostic, client logic owns external IO.
