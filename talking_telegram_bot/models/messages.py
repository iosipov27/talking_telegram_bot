from dataclasses import dataclass


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    text: str


@dataclass(frozen=True)
class ChatHistoryEntry:
    request: str
    response: str
    created_at: str


@dataclass(frozen=True)
class ChatSummary:
    text: str
    updated_at: str


@dataclass(frozen=True)
class ChatHistoryLog:
    summary: ChatSummary | None
    entries: list[ChatHistoryEntry]


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str
