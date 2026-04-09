


# AGENTS.md

## Purpose

This document defines strict architectural and coding rules for AI agents (Codex or similar).
Follow rules exactly. Do not reinterpret.

---

# Agent Instructions

- Use the `python-telegram-bot` library for Telegram communication in this repository.
- Use https://python-telegram-bot.org/ as the primary source of documentation and examples.
- Do not add alternative Telegram libraries unless the user explicitly asks for them.
- Do not add a database or any persistent storage layer unless the user explicitly asks for it.
- Treat every incoming Telegram message as fully independent from previous messages.
- Do not store or send conversation history to the LLM.
- Never log Telegram bot tokens, LLM credentials, `.env` values, or full URLs that contain secrets.
- Write application logs to both the console and `logs/bot.log`.
- Allow `/models` as a Telegram control command for listing Ollama models and switching the runtime model.
- The default LLM model must come from `.env`; runtime selection may override it until the process stops.

---

## Architecture

### Layers (mandatory)

0. Entry Point
1. Controller
2. Service
3. Client
4. Config
5. Models

Flow:

Telegram → Entry Point → Controller → Service → Client → Service → Controller → Telegram

---

## Responsibilities

### Entry Point

* Application bootstrap
* Dependency wiring (manual DI)
* Initialize Telegram bot
* Start polling loop

Forbidden:

* Business logic
* HTTP calls
* LLM interaction

---

### Controller

* Accept external input (Telegram)
* Extract raw data
* Call service
* Return response

Forbidden:

* Business logic
* Direct LLM calls
* HTTP calls

---

### Service

* Core application logic
* Input normalization
* Error handling (domain-level)
* Orchestration

Rules:

* Must not depend on Telegram
* Must not perform HTTP calls directly

---

### Client

* External communication (Ollama HTTP)
* Timeout handling
* Low-level error raising

Rules:

* No business logic
* No formatting for end users

---

### Config

* Read environment variables
* Provide typed settings

---

### Models

* Pure data structures
* No logic

---

## Dependency Rules

Allowed:

* Entry Point → Controller
* Controller → Service
* Service → Client
* Service → Models
* Client → Models

Forbidden:

* Controller → Client
* Client → Service
* Models → any layer

---

## Error Handling

* Client raises technical exceptions
* Service converts to domain errors
* Controller returns user-safe message

Never propagate raw exceptions to user.

---

## LLM Response Rules (strict)

Service layer MUST treat the following as errors:

* LLM timeout (no response in configured time)
* Empty response (`""` or missing content)
* Invalid response format
* Response generation taking too long (blocking behavior)

Behavior:

* Throw service-level error
* Do NOT return partial or undefined response
* Do NOT retry silently
* Do NOT attempt fallback generation inside client

Controller must:

* Return safe message:
  "LLM is currently unavailable. Please try again later."

---

## LLM Integration

* Use HTTP: `POST /api/chat`
* Always set `"stream": false`
* Always use timeout

---

## Telegram Mode

* Polling only
* Single text handler for regular user messages
* Explicit command/callback handlers are allowed for bot controls
* Ignore non-text input
* Process each text message independently without chat memory

---

## Persistence

* No database
* No message history storage
* No in-memory conversation state that affects future replies
* Exception: current LLM model may be stored in memory for runtime model switching

---

## Coding Principles

### Priority

1. Readability
2. Simplicity
3. Correctness
4. Maintainability
5. Flexibility (lowest priority)

---

### SOLID (strict)

* Single Responsibility — each class has one purpose
* Open/Closed — extend via new classes, not conditionals
* Liskov — no unexpected behavior in overrides
* Interface Segregation — no “fat” interfaces
* Dependency Inversion — depend on abstractions where needed

---

### KISS

* Prefer simplest working solution
* Avoid abstraction unless necessary

---

### DRY

* Remove duplication only if it improves readability
* Do NOT introduce abstractions just to remove small repetition

---

## Code Style Rules

* Small functions (≤ 30 lines)
* One responsibility per function
* Explicit naming (no abbreviations)
* Avoid deep nesting (>2 levels)

---

## State Management

* No global mutable state
* Pass dependencies via constructors
* No hidden side effects

---

## Validation

* Validate only at boundaries (Controller / Service entry)
* Do not scatter defensive checks everywhere
* Do not over-validate

---

## Error Strategy

* Fail fast inside layers
* Handle errors at service boundary
* Return safe fallback message

Avoid:

* excessive try/except
* silent failures
* defensive clutter

---

## Forbidden Patterns

* Fat controllers
* Direct HTTP calls from services or controllers
* Mixing layers
* “God classes”
* Over-engineering
* Premature abstraction
* Catch-all exception blocks without reason

---

## Allowed Simplifications

* Inline logic if abstraction adds complexity
* Duplicate small pieces if abstraction reduces clarity
* Use straightforward code over “clever” solutions

---

## Performance

* Use async for I/O (Telegram, HTTP)
* Do not optimize prematurely

---

## Extensibility

Future features must be added by:

* extending services
* adding new clients
* not modifying existing flow unnecessarily

---

## Summary

* Keep layers strict
* Keep code simple
* Treat invalid LLM responses as errors
* Optimize for human readability, not theoretical purity
