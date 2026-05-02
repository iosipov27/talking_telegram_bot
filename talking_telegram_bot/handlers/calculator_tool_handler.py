from __future__ import annotations

import logging
from dataclasses import asdict

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.events import ToolExecutionRequested
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.calculator_service import (
    CalculatorService,
    CalculatorServiceError,
)

logger = logging.getLogger(__name__)


class CalculatorToolHandler:
    def __init__(
        self,
        response_service: AgentResponseService,
        calculator_service: CalculatorService,
    ) -> None:
        self._response_service = response_service
        self._calculator_service = calculator_service

    async def handle(self, envelope: MessageEnvelope[ToolExecutionRequested]) -> None:
        if envelope.message.action != "calculator":
            return
        if envelope.message.response_future.done():
            return
        expression = envelope.message.args.get("expression")
        if not isinstance(expression, str):
            log_event(
                logger,
                logging.WARNING,
                log_events.AGENT_TOOL_FAILED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                tool_action=envelope.message.action,
                reason="invalid_expression",
            )
            envelope.message.response_future.set_result(
                self._response_service.build_error_observation(
                    "Tool calculator requires a string expression.",
                ),
            )
            return
        try:
            calculator_response = self._calculator_service.calculate(expression)
        except CalculatorServiceError as exc:
            log_event(
                logger,
                logging.ERROR,
                log_events.AGENT_TOOL_FAILED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                tool_action=envelope.message.action,
                error=str(exc),
            )
            envelope.message.response_future.set_exception(exc)
            return
        envelope.message.response_future.set_result(
            self._response_service.build_tool_observation(
                envelope.message.action,
                asdict(calculator_response),
            ),
        )
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_TOOL_COMPLETED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            tool_action=envelope.message.action,
        )
