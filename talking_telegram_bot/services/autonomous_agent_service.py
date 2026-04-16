from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.constants.prompt_settings import (
    AGENT_CONTINUE_PROMPT,
    AGENT_MAX_STEPS,
)
from talking_telegram_bot.models.agent import AgentToolCall
from talking_telegram_bot.models.messages import ConversationMessage
from talking_telegram_bot.services.search_web_service import (
    SearchWebService,
    SearchWebServiceError,
)


class AutonomousAgentError(RuntimeError):
    """Raised when the autonomous agent can not finish safely."""


class AutonomousAgentService:
    def __init__(
        self,
        ollama_client: OllamaClient,
        search_web_service: SearchWebService,
    ) -> None:
        self._ollama_client = ollama_client
        self._search_web_service = search_web_service

    async def run(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            ConversationMessage(role="system", content=system_prompt),
            ConversationMessage(role="user", content=user_prompt),
        ]
        for _ in range(AGENT_MAX_STEPS):
            response_text = await self._request_step(messages)
            payload = self._parse_json_object(response_text)
            if payload is None:
                return response_text
            final_answer = self._read_final_answer(payload)
            if final_answer is not None:
                return final_answer
            messages.append(
                ConversationMessage(role="assistant", content=response_text),
            )
            follow_up = await self._build_follow_up(payload)
            messages.append(ConversationMessage(role="user", content=follow_up))
        raise AutonomousAgentError("Agent exceeded the maximum number of steps.")

    async def _request_step(self, messages: list[ConversationMessage]) -> str:
        try:
            assistant_message = await self._ollama_client.generate_reply(messages)
        except OllamaClientError as exc:
            raise AutonomousAgentError("LLM is unavailable.") from exc
        response_text = assistant_message.text.strip()
        if response_text:
            return response_text
        raise AutonomousAgentError("LLM returned an empty response.")

    def _parse_json_object(self, response_text: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(response_text)
        except ValueError:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def _read_final_answer(self, payload: dict[str, Any]) -> str | None:
        final_answer = payload.get("final_answer")
        if isinstance(final_answer, str):
            return final_answer
        return None

    async def _build_follow_up(self, payload: dict[str, Any]) -> str:
        tool_call = self._read_tool_call(payload)
        if tool_call is None:
            return AGENT_CONTINUE_PROMPT
        if tool_call.action != "search_web":
            return self._build_error_observation(
                f"Unknown tool: {tool_call.action}.",
            )
        query = tool_call.args.get("query")
        if not isinstance(query, str):
            return self._build_error_observation(
                "Tool search_web requires a string query.",
            )
        try:
            search_response = await self._search_web_service.search_web(query)
        except SearchWebServiceError as exc:
            raise AutonomousAgentError("Web search is unavailable.") from exc
        return json.dumps(
            {
                "tool_name": tool_call.action,
                "tool_result": {
                    "query": search_response.query,
                    "results": [asdict(result) for result in search_response.results],
                },
            },
            ensure_ascii=False,
        )

    def _read_tool_call(self, payload: dict[str, Any]) -> AgentToolCall | None:
        action = payload.get("action")
        args = payload.get("args")
        if not isinstance(action, str) or not isinstance(args, dict):
            return None
        return AgentToolCall(action=action, args=args)

    def _build_error_observation(self, error_message: str) -> str:
        return json.dumps(
            {"tool_error": error_message},
            ensure_ascii=False,
        )

