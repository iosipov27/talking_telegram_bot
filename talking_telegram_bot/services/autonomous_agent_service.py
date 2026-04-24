from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
import logging
from datetime import datetime

from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.prompt_settings import AGENT_MAX_STEPS
from talking_telegram_bot.constants.user_messages import FINAL_CHECK_PROGRESS_MESSAGE
from talking_telegram_bot.logging_utils import MarkdownTable, format_markdown_event
from talking_telegram_bot.models.messages import ConversationMessage
from talking_telegram_bot.services.agent_request_builder_service import (
    AgentRequestBuilderService,
)
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.agent_tool_service import (
    AgentToolExecutionError,
    AgentToolService,
)
from talking_telegram_bot.services.calculator_service import CalculatorService
from talking_telegram_bot.services.search_web_service import SearchWebService
from talking_telegram_bot.services.weather_service import WeatherService

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str], Awaitable[None]]


class AutonomousAgentError(RuntimeError):
    """Raised when the autonomous agent can not finish safely."""


class AutonomousAgentService:
    def __init__(
        self,
        ollama_client: OllamaClient,
        search_web_service: SearchWebService,
        calculator_service: CalculatorService,
        weather_service: WeatherService | None = None,
        request_builder_service: AgentRequestBuilderService | None = None,
        response_service: AgentResponseService | None = None,
        tool_service: AgentToolService | None = None,
    ) -> None:
        self._ollama_client = ollama_client
        self._request_builder_service = (
            request_builder_service
            or AgentRequestBuilderService(lambda: self._get_current_datetime_iso())
        )
        self._response_service = response_service or AgentResponseService()
        self._tool_service = tool_service or AgentToolService(
            self._response_service,
            search_web_service,
            calculator_service,
            weather_service,
        )

    async def run(
        self,
        system_prompt: str,
        user_prompt: str,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        messages = [
            ConversationMessage(role="system", content=system_prompt),
            ConversationMessage(role="user", content=user_prompt),
        ]
        for step_number in range(1, AGENT_MAX_STEPS + 1):
            if step_number > 1:
                await self._report_progress(
                    progress_callback,
                    FINAL_CHECK_PROGRESS_MESSAGE,
                )
            response_text = await self._request_step(messages)
            payload = self._response_service.parse_json_object(response_text)
            if payload is None:
                final_answer = self._response_service.read_final_answer_from_text(
                    response_text,
                )
                if final_answer is not None:
                    return final_answer
                return response_text
            self._log_thought(step_number, payload)
            final_answer = self._response_service.read_final_answer(payload)
            if final_answer is not None:
                return final_answer
            messages.append(
                ConversationMessage(role="assistant", content=response_text),
            )
            follow_up = await self._build_follow_up(payload, progress_callback)
            messages.append(ConversationMessage(role="user", content=follow_up))
        raise AutonomousAgentError("Agent exceeded the maximum number of steps.")

    async def _request_step(self, messages: list[ConversationMessage]) -> str:
        request_messages = self._request_builder_service.build_request_messages(messages)
        try:
            assistant_message = await self._ollama_client.generate_reply(request_messages)
        except OllamaClientError as exc:
            raise AutonomousAgentError("LLM is unavailable.") from exc
        response_text = assistant_message.text.strip()
        if response_text:
            return response_text
        raise AutonomousAgentError("LLM returned an empty response.")

    def _get_current_datetime_iso(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    async def _build_follow_up(
        self,
        payload: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> str:
        try:
            return await self._tool_service.build_follow_up(payload, progress_callback)
        except AgentToolExecutionError as exc:
            raise AutonomousAgentError(str(exc)) from exc

    async def _report_progress(
        self,
        progress_callback: ProgressCallback | None,
        message: str,
    ) -> None:
        if progress_callback is None:
            return
        await progress_callback(message)

    def _log_thought(self, step_number: int, payload: dict[str, Any]) -> None:
        thought = payload.get("thought")
        if not isinstance(thought, str) or not thought.strip():
            return
        action = payload.get("action")
        logger.info(
            format_markdown_event(
                log_events.AGENT_THOUGHT_RECEIVED,
                [
                    ("Step", step_number),
                    ("Action", action if isinstance(action, str) else "-"),
                ],
                detail_tables=[
                    MarkdownTable(
                        headers=("Type", "Content"),
                        rows=(("thought", thought),),
                    ),
                ],
            ),
        )
