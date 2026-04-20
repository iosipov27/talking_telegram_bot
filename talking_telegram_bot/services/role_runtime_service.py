from __future__ import annotations

import re

from talking_telegram_bot.constants.prompt_settings import DEFAULT_AGENT_ROLE


class RoleRuntimeError(RuntimeError):
    """Raised when the runtime role is invalid."""


class RoleRuntimeService:
    def __init__(self, agent_role: str = DEFAULT_AGENT_ROLE) -> None:
        self._agent_role = self._normalize_role(agent_role)

    def get_current_agent_role(self) -> str:
        return self._agent_role

    def set_agent_role(self, raw_role: str) -> str:
        self._agent_role = self._normalize_role(raw_role)
        return self._agent_role

    def _normalize_role(self, raw_role: str) -> str:
        normalized_role = raw_role.strip()
        normalized_role = normalized_role.replace("<role>", "")
        normalized_role = normalized_role.replace("</role>", "")
        normalized_role = normalized_role.strip()
        normalized_role = re.sub(
            r"^ты[\s—-]+",
            "",
            normalized_role,
            flags=re.IGNORECASE,
        )
        if normalized_role:
            return normalized_role
        raise RoleRuntimeError("Agent role is empty.")

