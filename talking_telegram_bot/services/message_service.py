import re

from talking_telegram_bot.constants.prompt_settings import AGENT_SYSTEM_PROMPT, DEFAULT_AGENT_ROLE
from talking_telegram_bot.models.messages import ConversationMessage, UserMessage
from talking_telegram_bot.services.autonomous_agent_service import (
    AutonomousAgentError,
    AutonomousAgentService,
)


class MessageProcessingError(RuntimeError):
    """Raised when a user message can not be processed safely."""


class AgentRoleSelectionError(RuntimeError):
    """Raised when the runtime agent role is invalid."""


class AgentRoleUpdateError(RuntimeError):
    """Raised when the runtime agent role can not be updated safely."""


class MessageService:
    def __init__(
        self,
        agent_service: AutonomousAgentService,
        agent_role: str = DEFAULT_AGENT_ROLE,
    ) -> None:
        self._agent_service = agent_service
        self._agent_role = self._normalize_agent_role(agent_role)

    async def generate_reply(self, raw_text: str, user_id: int) -> str:
        del user_id
        user_message = self._normalize_message(raw_text)
        try:
            reply_text = await self._agent_service.run(
                self._build_system_prompt().content,
                user_message.text,
            )
        except AutonomousAgentError as exc:
            raise MessageProcessingError("LLM is unavailable.") from exc
        reply_text = reply_text.strip()
        if not reply_text:
            raise MessageProcessingError("LLM returned an empty response.")
        return reply_text

    def get_current_agent_role(self) -> str:
        return self._agent_role

    def set_agent_role(self, raw_role: str) -> str:
        self._agent_role = self._normalize_agent_role(raw_role)
        return self._agent_role

    async def update_agent_role(self, raw_role: str, user_id: int) -> str:
        del user_id
        selected_role = self._normalize_agent_role(raw_role)
        self._agent_role = selected_role
        return selected_role

    def _normalize_message(self, raw_text: str) -> UserMessage:
        normalized_text = raw_text.strip()
        if normalized_text:
            return UserMessage(text=normalized_text)
        raise MessageProcessingError("Message text is empty.")

    def _normalize_agent_role(self, raw_role: str) -> str:
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
        raise AgentRoleSelectionError("Agent role is empty.")

    def _build_system_prompt(self) -> ConversationMessage:
        return ConversationMessage(
            role="system",
            content=AGENT_SYSTEM_PROMPT.format(agent_role=self._agent_role),
        )
