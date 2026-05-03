from __future__ import annotations

from dataclasses import asdict

from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants.user_messages import WEATHER_LOOKUP_PROGRESS_MESSAGE
from talking_telegram_bot.messages.events import ProgressUpdated
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.agent_tool_dispatcher_service import (
    AgentToolContext,
    AgentToolExecutionError,
)
from talking_telegram_bot.services.weather_service import (
    WeatherService,
    WeatherServiceError,
)


class WeatherToolHandler:
    action_name = "weather"

    def __init__(
        self,
        response_service: AgentResponseService,
        weather_service: WeatherService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._response_service = response_service
        self._weather_service = weather_service
        self._event_bus = event_bus

    async def execute(
        self,
        args: dict[str, object],
        context: AgentToolContext,
    ) -> str:
        location = args.get("location")
        if not isinstance(location, str):
            return self._response_service.build_error_observation(
                "Tool weather requires a string location.",
            )
        await self._event_bus.publish(
            ProgressUpdated(text=WEATHER_LOOKUP_PROGRESS_MESSAGE),
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            chat_id=context.chat_id,
            user_id=context.user_id,
        )
        try:
            weather_response = await self._weather_service.get_weather(location)
        except WeatherServiceError as exc:
            raise AgentToolExecutionError(str(exc)) from exc
        return self._response_service.build_tool_observation(
            self.action_name,
            asdict(weather_response),
        )
