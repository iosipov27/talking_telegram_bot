from __future__ import annotations

import logging
from dataclasses import asdict

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.agent_tool_dispatcher_service import AgentToolContext
from talking_telegram_bot.services.calculator_service import (
    CalculatorService,
    CalculatorServiceError,
)

logger = logging.getLogger(__name__)


class CalculatorToolHandler:
    action_name = "calculator"

    def __init__(
        self,
        response_service: AgentResponseService,
        calculator_service: CalculatorService,
    ) -> None:
        self._response_service = response_service
        self._calculator_service = calculator_service

    async def execute(
        self,
        args: dict[str, object],
        context: AgentToolContext,
    ) -> str:
        expression = args.get("expression")
        if not isinstance(expression, str):
            log_event(
                logger,
                logging.WARNING,
                log_events.AGENT_TOOL_FAILED,
                trace_id=context.correlation_id,
                chat_id=context.chat_id,
                user_id=context.user_id,
                tool_action=self.action_name,
                reason="invalid_expression",
            )
            return self._response_service.build_error_observation(
                "Tool calculator requires a string expression.",
            )
        try:
            calculator_response = self._calculator_service.calculate(expression)
        except CalculatorServiceError as exc:
            log_event(
                logger,
                logging.ERROR,
                log_events.AGENT_TOOL_FAILED,
                trace_id=context.correlation_id,
                chat_id=context.chat_id,
                user_id=context.user_id,
                tool_action=self.action_name,
                error=str(exc),
            )
            raise
        observation = self._response_service.build_tool_observation(
            self.action_name,
            asdict(calculator_response),
        )
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_TOOL_COMPLETED,
            trace_id=context.correlation_id,
            chat_id=context.chat_id,
            user_id=context.user_id,
            tool_action=self.action_name,
        )
        return observation
