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
class ConversationMessage:
    role: str
    content: str
