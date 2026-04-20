from __future__ import annotations

from talking_telegram_bot.constants.prompt_settings import AGENT_SYSTEM_PROMPT
from talking_telegram_bot.services.role_runtime_service import RoleRuntimeService


class PromptBuilderService:
    def __init__(self, role_runtime_service: RoleRuntimeService) -> None:
        self._role_runtime_service = role_runtime_service

    def build_system_prompt(self) -> str:
        return AGENT_SYSTEM_PROMPT.format(
            agent_role=self._role_runtime_service.get_current_agent_role(),
        )

