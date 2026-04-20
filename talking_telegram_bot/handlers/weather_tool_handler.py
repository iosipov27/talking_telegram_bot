from __future__ import annotations

from dataclasses import asdict

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants.user_messages import WEATHER_LOOKUP_PROGRESS_MESSAGE
from talking_telegram_bot.messages.events import ProgressUpdated, ToolExecutionRequested
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.weather_service import (
    WeatherService,
    WeatherServiceError,
)


class WeatherToolHandler:
    def __init__(
        self,
        response_service: AgentResponseService,
        weather_service: WeatherService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._response_service = response_service
        self._weather_service = weather_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[ToolExecutionRequested]) -> None:
        if envelope.message.action != "weather":
            return
        if envelope.message.response_future.done():
            return
        location = envelope.message.args.get("location")
        if not isinstance(location, str):
            envelope.message.response_future.set_result(
                self._response_service.build_error_observation(
                    "Tool weather requires a string location.",
                ),
            )
            return
        await self._event_bus.publish(
            ProgressUpdated(text=WEATHER_LOOKUP_PROGRESS_MESSAGE),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        try:
            weather_response = await self._weather_service.get_weather(location)
        except WeatherServiceError as exc:
            envelope.message.response_future.set_exception(exc)
            return
        envelope.message.response_future.set_result(
            self._response_service.build_tool_observation(
                envelope.message.action,
                asdict(weather_response),
            ),
        )

