from __future__ import annotations

from dataclasses import asdict

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.messages.events import ToolExecutionRequested
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.calculator_service import (
    CalculatorService,
    CalculatorServiceError,
)


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
            envelope.message.response_future.set_result(
                self._response_service.build_error_observation(
                    "Tool calculator requires a string expression.",
                ),
            )
            return
        try:
            calculator_response = self._calculator_service.calculate(expression)
        except CalculatorServiceError as exc:
            envelope.message.response_future.set_exception(exc)
            return
        envelope.message.response_future.set_result(
            self._response_service.build_tool_observation(
                envelope.message.action,
                asdict(calculator_response),
            ),
        )

