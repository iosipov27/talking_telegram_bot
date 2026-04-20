from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from talking_telegram_bot.constants.prompt_settings import AGENT_CONTINUE_PROMPT
from talking_telegram_bot.constants.user_messages import (
    WEB_RESULTS_PROGRESS_MESSAGE,
    WEB_SEARCH_PROGRESS_MESSAGE,
)
from talking_telegram_bot.models.agent import AgentToolCall
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.calculator_service import (
    CalculatorService,
    CalculatorServiceError,
)
from talking_telegram_bot.services.search_web_service import (
    SearchWebService,
    SearchWebServiceError,
)

ProgressCallback = Callable[[str], Awaitable[None]]


class AgentToolExecutionError(RuntimeError):
    """Raised when an agent tool can not finish safely."""


class AgentToolService:
    def __init__(
        self,
        response_service: AgentResponseService,
        search_web_service: SearchWebService,
        calculator_service: CalculatorService,
    ) -> None:
        self._response_service = response_service
        self._search_web_service = search_web_service
        self._calculator_service = calculator_service

    async def build_follow_up(
        self,
        payload: dict[str, Any],
        progress_callback: ProgressCallback | None,
    ) -> str:
        tool_call = self._response_service.read_tool_call(payload)
        if tool_call is None:
            return AGENT_CONTINUE_PROMPT
        if tool_call.action == "search_web":
            return await self._run_search_web(tool_call, progress_callback)
        if tool_call.action == "calculator":
            return self._run_calculator(tool_call)
        return self._response_service.build_error_observation(
            f"Unknown tool: {tool_call.action}.",
        )

    async def _run_search_web(
        self,
        tool_call: AgentToolCall,
        progress_callback: ProgressCallback | None,
    ) -> str:
        query = tool_call.args.get("query")
        if not isinstance(query, str):
            return self._response_service.build_error_observation(
                "Tool search_web requires a string query.",
            )
        await self._report_progress(progress_callback, WEB_SEARCH_PROGRESS_MESSAGE)
        try:
            search_response = await self._search_web_service.search_web(query)
        except SearchWebServiceError as exc:
            raise AgentToolExecutionError("Web search is unavailable.") from exc
        await self._report_progress(progress_callback, WEB_RESULTS_PROGRESS_MESSAGE)
        return self._response_service.build_tool_observation(
            tool_call.action,
            {
                "query": search_response.query,
                "results": [asdict(result) for result in search_response.results],
            },
        )

    def _run_calculator(self, tool_call: AgentToolCall) -> str:
        expression = tool_call.args.get("expression")
        if not isinstance(expression, str):
            return self._response_service.build_error_observation(
                "Tool calculator requires a string expression.",
            )
        try:
            calculator_response = self._calculator_service.calculate(expression)
        except CalculatorServiceError as exc:
            raise AgentToolExecutionError("Calculator is unavailable.") from exc
        return self._response_service.build_tool_observation(
            tool_call.action,
            asdict(calculator_response),
        )

    async def _report_progress(
        self,
        progress_callback: ProgressCallback | None,
        message: str,
    ) -> None:
        if progress_callback is None:
            return
        await progress_callback(message)
