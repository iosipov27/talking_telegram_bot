from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.handlers.process_text_message_handler import (
    ProcessTextMessageHandler,
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
)
from talking_telegram_bot.models.weather import WeatherForecastDay, WeatherResponse
from talking_telegram_bot.services.agent_request_orchestrator_service import (
    AgentRequestOrchestratorService,
)
from talking_telegram_bot.services.message_input_service import MessageInputService
from talking_telegram_bot.services.prompt_builder_service import PromptBuilderService
from talking_telegram_bot.services.weather_query_router_service import (
    WeatherQueryRouterService,
)
from talking_telegram_bot.services.weather_reply_formatter_service import (
    WeatherReplyFormatterService,
)
from talking_telegram_bot.services.weather_service import WeatherService


class ProcessTextMessageHandlerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_routes_weather_query_without_date_before_agent(self) -> None:
        event_bus = AsyncMock()
        weather_service = AsyncMock(spec=WeatherService)
        weather_service.get_weather.return_value = WeatherResponse(
            requested_location="Rome",
            resolved_location="Rome",
            region="Lazio",
            country="Italy",
            observation_time="2026-04-21 12:00 PM",
            condition="Sunny",
            temp_c="20",
            temp_f="68",
            feels_like_c="20",
            feels_like_f="68",
            humidity="40",
            wind_speed_kmph="10",
            wind_speed_miles="6",
            wind_direction="SW",
            visibility_km="10",
            forecast=[
                WeatherForecastDay(
                    date="2026-04-21",
                    condition="Sunny",
                    min_temp_c="12",
                    max_temp_c="22",
                    min_temp_f="54",
                    max_temp_f="72",
                    sunrise="06:10 AM",
                    sunset="07:58 PM",
                ),
            ],
        )
        formatter = Mock(spec=WeatherReplyFormatterService)
        formatter.format_reply.return_value = "weather reply"
        handler = ProcessTextMessageHandler(
            MessageInputService(),
            AgentRequestOrchestratorService(
                Mock(spec=PromptBuilderService),
                event_bus,
            ),
            event_bus,
            WeatherQueryRouterService(),
            weather_service,
            formatter,
        )
        envelope = MessageEnvelope(
            message=ProcessTextMessage(message=object(), raw_text="Какая погода в Риме?"),
            correlation_id="corr-1",
            user_id=123,
        )

        await handler.handle(envelope)

        weather_service.get_weather.assert_awaited_once_with("Риме")
        event_bus.publish_and_wait.assert_any_await(
            MessageReceived(text="Какая погода в Риме?"),
            correlation_id="corr-1",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
        event_bus.publish_and_wait.assert_any_await(
            StartTelegramResponseSession(message=envelope.message.message),
            correlation_id="corr-1",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
        event_bus.publish_and_wait.assert_any_await(
            ResponseGenerated(text="weather reply"),
            correlation_id="corr-1",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
        event_bus.publish.assert_awaited_once()
        published_progress = event_bus.publish.await_args.args[0]
        self.assertIsInstance(published_progress, ProgressUpdated)
        self.assertEqual(published_progress.text, "Проверяю погоду...")
        event_bus.publish_and_wait.assert_any_await(
            ReplyReady(text="weather reply"),
            correlation_id="corr-1",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )

    async def test_routes_weather_query_without_location_to_clarification(self) -> None:
        event_bus = AsyncMock()
        handler = ProcessTextMessageHandler(
            MessageInputService(),
            AgentRequestOrchestratorService(
                Mock(spec=PromptBuilderService),
                event_bus,
            ),
            event_bus,
            WeatherQueryRouterService(),
            AsyncMock(spec=WeatherService),
            Mock(spec=WeatherReplyFormatterService),
        )
        envelope = MessageEnvelope(
            message=ProcessTextMessage(message=object(), raw_text="Какая погода?"),
            correlation_id="corr-2",
            user_id=123,
        )

        await handler.handle(envelope)

        event_bus.publish_and_wait.assert_any_await(
            MessageReceived(text="Какая погода?"),
            correlation_id="corr-2",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
        event_bus.publish_and_wait.assert_any_await(
            ResponseGenerated(
                text="Please specify the city or place for the weather lookup.",
            ),
            correlation_id="corr-2",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
        event_bus.publish_and_wait.assert_any_await(
            TextReplyRequested(
                message=envelope.message.message,
                text="Please specify the city or place for the weather lookup.",
            ),
            correlation_id="corr-2",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )

    async def test_does_not_route_weather_query_with_date(self) -> None:
        event_bus = AsyncMock()
        prompt_builder_service = Mock(spec=PromptBuilderService)
        prompt_builder_service.build_system_prompt.return_value = "system"
        weather_service = AsyncMock(spec=WeatherService)
        handler = ProcessTextMessageHandler(
            MessageInputService(),
            AgentRequestOrchestratorService(
                prompt_builder_service,
                event_bus,
            ),
            event_bus,
            WeatherQueryRouterService(),
            weather_service,
            Mock(spec=WeatherReplyFormatterService),
        )
        envelope = MessageEnvelope(
            message=ProcessTextMessage(
                message=object(),
                raw_text="Какая погода будет в Риме 30 апреля?",
            ),
            correlation_id="corr-3",
            user_id=123,
        )

        await handler.handle(envelope)

        weather_service.get_weather.assert_not_called()
        event_bus.publish_and_wait.assert_any_await(
            MessageReceived(text="Какая погода будет в Риме 30 апреля?"),
            correlation_id="corr-3",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
        event_bus.publish_and_wait.assert_any_await(
            StartTelegramResponseSession(message=envelope.message.message),
            correlation_id="corr-3",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
        event_bus.publish_and_wait.assert_any_await(
            AgentRunRequested(
                system_prompt="system",
                user_prompt="Какая погода будет в Риме 30 апреля?",
            ),
            correlation_id="corr-3",
            causation_id=envelope.message_id,
            chat_id=None,
            user_id=123,
        )
