from __future__ import annotations

import json
from typing import Any

from talking_telegram_bot.models.agent import AgentToolCall


class AgentResponseService:
    def parse_json_object(self, response_text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(response_text)
        except ValueError:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def read_final_answer(self, payload: dict[str, Any]) -> str | None:
        final_answer = payload.get("final_answer")
        if isinstance(final_answer, str):
            return final_answer
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

    def read_tool_call(self, payload: dict[str, Any]) -> AgentToolCall | None:
        action = payload.get("action")
        args = payload.get("args")
        if not isinstance(action, str) or not isinstance(args, dict):
            return None
        return AgentToolCall(action=action, args=args)

    def build_tool_observation(
        self,
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> str:
        return json.dumps(
            {
                "tool_name": tool_name,
                "tool_result": tool_result,
            },
            ensure_ascii=False,
        )

    def build_error_observation(self, error_message: str) -> str:
        return json.dumps(
            {"tool_error": error_message},
            ensure_ascii=False,
        )

    def _read_final_response_value(self, payload: dict[str, Any]) -> str | None:
        for key in ("response", "answer"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return None
