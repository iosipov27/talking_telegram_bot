# ADR 0001: Single-Process Event-Driven Bot

## Status

Accepted.

## Context

The application is a Telegram polling bot with a small set of use cases:

- text messages;
- document messages;
- model and role commands;
- a multi-step local Ollama agent loop;
- a few deterministic tools and external API lookups.

The project does not need a database, service mesh, API gateway, or distributed message broker for the current scope.

## Decision

Use a single Python process with in-memory command and event buses:

- inbound Telegram controllers translate updates into commands;
- command handlers own use-case entry points;
- event subscribers handle outbound Telegram updates, history, and workflow triggers;
- `AgentRunWorkflow` owns the agent loop;
- `AgentToolDispatcherService` executes agent tools directly with a timeout.

## Consequences

This keeps the runtime simple, readable, and easy to run locally. It also keeps future extraction possible because commands, events, services, and clients already have explicit boundaries.

The tradeoff is that bus state and runtime selections are in memory. A process restart loses active sessions, selected model, and selected role, which matches the current runtime rules.
