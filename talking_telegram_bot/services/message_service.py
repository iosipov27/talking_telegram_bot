import json
import re
from typing import Any

from talking_telegram_bot.constants.prompt_settings import AGENT_SYSTEM_PROMPT, DEFAULT_AGENT_ROLE
from talking_telegram_bot.logging_utils import build_markdown_table
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
        return self._format_json_reply(reply_text)

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

    def _format_json_reply(self, reply_text: str) -> str:
        payload = self._parse_json_object(reply_text)
        if payload is None:
            return reply_text
        final_response = self._extract_final_response(payload)
        if final_response is not None:
            return final_response
        rows = tuple(self._build_json_rows(payload))
        if not rows:
            return reply_text
        return build_markdown_table(("Field", "Value"), rows)

    def _parse_json_object(self, reply_text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(reply_text)
        except ValueError:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def _extract_final_response(self, payload: dict[str, Any]) -> str | None:
        final_answer = payload.get("final_answer")
        if isinstance(final_answer, str) and final_answer.strip():
            return final_answer.strip()
        action = payload.get("action")
        if action == "final_response":
            response = self._read_final_response_value(payload)
            if response is not None:
                return response
            args = payload.get("args")
            if not isinstance(args, dict):
                return None
            return self._read_final_response_value(args)
        return None

    def _read_final_response_value(self, payload: dict[str, Any]) -> str | None:
        for key in ("response", "answer"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _build_json_rows(
        self,
        payload: dict[str, Any],
    ) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        self._append_json_rows(payload, "", rows)
        return rows

    def _append_json_rows(
        self,
        value: Any,
        prefix: str,
        rows: list[tuple[str, str]],
    ) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                field_name = f"{prefix}.{key}" if prefix else key
                if isinstance(nested_value, dict):
                    self._append_json_rows(nested_value, field_name, rows)
                    continue
                rows.append((field_name, self._format_json_value(nested_value)))
            return
        rows.append((prefix or "value", self._format_json_value(value)))

    def _format_json_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)
