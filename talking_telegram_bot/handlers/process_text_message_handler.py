from __future__ import annotations

import logging

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.user_messages import (
    SAFE_LLM_ERROR_MESSAGE,
    SAFE_WEATHER_ERROR_MESSAGE,
    WEATHER_LOCATION_REQUIRED_MESSAGE,
    WEATHER_LOOKUP_PROGRESS_MESSAGE,
)
from talking_telegram_bot.messages.commands import ProcessTextMessage
from talking_telegram_bot.messages.events import (
    ProgressUpdated,
    ReplyReady,
    ResponseGenerated,
    StartTelegramResponseSession,
    TextReplyRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.services.agent_request_orchestrator_service import (
    AgentRequestOrchestratorService,
)
from talking_telegram_bot.services.message_input_service import (
    MessageInputError,
    MessageInputService,
)
from talking_telegram_bot.services.weather_query_router_service import (
    WeatherQueryRouterService,
)
from talking_telegram_bot.services.weather_reply_formatter_service import (
    WeatherReplyFormatterService,
)
from talking_telegram_bot.services.weather_service import WeatherService, WeatherServiceError

logger = logging.getLogger(__name__)


class ProcessTextMessageHandler:
    def __init__(
        self,
        message_input_service: MessageInputService,
        agent_request_orchestrator_service: AgentRequestOrchestratorService,
        event_bus: InMemoryEventBus,
        weather_query_router_service: WeatherQueryRouterService,
        weather_service: WeatherService,
        weather_reply_formatter_service: WeatherReplyFormatterService,
    ) -> None:
        self._message_input_service = message_input_service
        self._agent_request_orchestrator_service = agent_request_orchestrator_service
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
            log_event(
                logger,
                logging.WARNING,
                log_events.TEXT_MESSAGE_PROCESSING_ERROR,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                reason="empty_text",
            )
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
        log_event(
            logger,
            logging.INFO,
            log_events.TEXT_MESSAGE_NORMALIZED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            text_length=len(user_prompt),
        )
        await self._agent_request_orchestrator_service.publish_message_received(
            envelope,
            user_prompt,
        )
        weather_route = self._weather_query_router_service.route(user_prompt)
        if weather_route.should_route:
            log_event(
                logger,
                logging.INFO,
                log_events.WEATHER_ROUTE_SELECTED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                has_location=bool(weather_route.location),
            )
            await self._handle_weather_route(envelope, weather_route.location)
            return
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_ROUTE_SELECTED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        try:
            await self._agent_request_orchestrator_service.start_agent_response(
                envelope,
                envelope.message.message,
                user_prompt,
                "text",
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                log_events.TEXT_MESSAGE_PROCESSING_ERROR,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                reason="agent_request_failed",
                exc_info=True,
            )
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
            log_event(
                logger,
                logging.INFO,
                log_events.WEATHER_ROUTE_REJECTED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                reason="missing_location",
            )
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
            log_event(
                logger,
                logging.ERROR,
                log_events.WEATHER_ROUTE_REJECTED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                reason="lookup_failed",
                exc_info=True,
            )
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
