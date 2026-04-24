from __future__ import annotations

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants.user_messages import (
    SAFE_LLM_ERROR_MESSAGE,
    SAFE_WEATHER_ERROR_MESSAGE,
    WEATHER_LOCATION_REQUIRED_MESSAGE,
    WEATHER_LOOKUP_PROGRESS_MESSAGE,
)
from talking_telegram_bot.messages.commands import ProcessTextMessage
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    MessageReceived,
    ProgressUpdated,
    ReplyReady,
    ResponseGenerated,
    StartTelegramResponseSession,
    TextReplyRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.services.message_input_service import (
    MessageInputError,
    MessageInputService,
)
from talking_telegram_bot.services.prompt_builder_service import PromptBuilderService
from talking_telegram_bot.services.weather_query_router_service import (
    WeatherQueryRouterService,
)
from talking_telegram_bot.services.weather_reply_formatter_service import (
    WeatherReplyFormatterService,
)
from talking_telegram_bot.services.weather_service import WeatherService, WeatherServiceError


class ProcessTextMessageHandler:
    def __init__(
        self,
        message_input_service: MessageInputService,
        prompt_builder_service: PromptBuilderService,
        event_bus: InMemoryEventBus,
        weather_query_router_service: WeatherQueryRouterService,
        weather_service: WeatherService,
        weather_reply_formatter_service: WeatherReplyFormatterService,
    ) -> None:
        self._message_input_service = message_input_service
        self._prompt_builder_service = prompt_builder_service
        self._event_bus = event_bus
        self._weather_query_router_service = weather_query_router_service
        self._weather_service = weather_service
        self._weather_reply_formatter_service = weather_reply_formatter_service

    async def handle(self, envelope: MessageEnvelope[ProcessTextMessage]) -> None:
        try:
            user_prompt = self._message_input_service.normalize_text(
                envelope.message.raw_text,
            )
        except MessageInputError:
            await self._publish_response_generated(envelope, SAFE_LLM_ERROR_MESSAGE)
            await self._event_bus.publish_and_wait(
                TextReplyRequested(
                    message=envelope.message.message,
                    text=SAFE_LLM_ERROR_MESSAGE,
                ),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
            return
        await self._publish_message_received(envelope, user_prompt)
        weather_route = self._weather_query_router_service.route(user_prompt)
        if weather_route.should_route:
            await self._handle_weather_route(envelope, weather_route.location)
            return
        await self._event_bus.publish_and_wait(
            StartTelegramResponseSession(message=envelope.message.message),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        try:
            await self._event_bus.publish_and_wait(
                AgentRunRequested(
                    system_prompt=self._prompt_builder_service.build_system_prompt(),
                    user_prompt=user_prompt,
                ),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
        except Exception:
            await self._event_bus.publish_and_wait(
                UserFacingErrorRaised(text=SAFE_LLM_ERROR_MESSAGE),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )

    async def _handle_weather_route(
        self,
        envelope: MessageEnvelope[ProcessTextMessage],
        location: str | None,
    ) -> None:
        if not location:
            await self._publish_response_generated(
                envelope,
                WEATHER_LOCATION_REQUIRED_MESSAGE,
            )
            await self._event_bus.publish_and_wait(
                TextReplyRequested(
                    message=envelope.message.message,
                    text=WEATHER_LOCATION_REQUIRED_MESSAGE,
                ),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
            return
        await self._event_bus.publish_and_wait(
            StartTelegramResponseSession(message=envelope.message.message),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        await self._event_bus.publish(
            ProgressUpdated(text=WEATHER_LOOKUP_PROGRESS_MESSAGE),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        try:
            weather_response = await self._weather_service.get_weather(location)
        except WeatherServiceError:
            await self._publish_response_generated(envelope, SAFE_WEATHER_ERROR_MESSAGE)
            await self._event_bus.publish_and_wait(
                UserFacingErrorRaised(text=SAFE_WEATHER_ERROR_MESSAGE),
                correlation_id=envelope.correlation_id,
                causation_id=envelope.message_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
            )
            return
        reply_text = self._weather_reply_formatter_service.format_reply(weather_response)
        await self._publish_response_generated(envelope, reply_text)
        await self._event_bus.publish_and_wait(
            ReplyReady(text=reply_text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )

    async def _publish_message_received(
        self,
        envelope: MessageEnvelope[ProcessTextMessage],
        text: str,
    ) -> None:
        await self._event_bus.publish_and_wait(
            MessageReceived(text=text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )

    async def _publish_response_generated(
        self,
        envelope: MessageEnvelope[ProcessTextMessage],
        text: str,
    ) -> None:
        await self._event_bus.publish_and_wait(
            ResponseGenerated(text=text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
