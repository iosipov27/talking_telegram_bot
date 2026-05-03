# ADR 0002: Client-Owned External IO

## Status

Accepted.

## Context

The bot talks to several external systems:

- Telegram through `python-telegram-bot`;
- Ollama through `/api/chat` and `/api/tags`;
- Tavily for current web search;
- Nominatim for location normalization;
- `wttr.in` for weather.

Mixing raw HTTP calls into services would make business logic harder to test and would spread low-level error handling across the codebase.

## Decision

External communication belongs in clients:

- clients own raw HTTP calls, payload parsing, timeouts, and technical exceptions;
- services call clients and convert client failures into service-level errors;
- controllers convert Telegram updates into commands and keep Telegram-specific IO at the boundary.

## Consequences

The service layer stays transport-agnostic and easier to unit test. Replacing an external provider or changing payload parsing is localized to a client plus its focused tests.

The tradeoff is a small amount of extra ceremony for each integration, which is acceptable because it preserves the project ownership rule: services must not perform raw `httpx` calls directly.
