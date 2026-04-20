from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StartTelegramResponseSession:
    message: Any


@dataclass(frozen=True, slots=True)
class ProgressUpdated:
    text: str


@dataclass(frozen=True, slots=True)
class ReplyReady:
    text: str


@dataclass(frozen=True, slots=True)
class UserFacingErrorRaised:
    text: str
    fallback_message: Any | None = None


@dataclass(frozen=True, slots=True)
class TextReplyRequested:
    message: Any
    text: str


@dataclass(frozen=True, slots=True)
class CallbackTextRequested:
    callback_query: Any
    text: str


@dataclass(frozen=True, slots=True)
class ModelListReady:
    message: Any
    current_model: str
    model_names: list[str]


@dataclass(frozen=True, slots=True)
class AgentRunRequested:
    system_prompt: str
    user_prompt: str


@dataclass(slots=True)
class ToolExecutionRequested:
    action: str
    args: dict[str, Any]
    response_future: asyncio.Future[str] = field(repr=False)

