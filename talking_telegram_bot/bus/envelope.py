from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import uuid4

MessageT = TypeVar("MessageT")


@dataclass(slots=True)
class MessageEnvelope(Generic[MessageT]):
    message: MessageT
    message_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    causation_id: str | None = None
    chat_id: int | None = None
    user_id: int | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

