from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentToolCall:
    action: str
    args: dict[str, Any]

