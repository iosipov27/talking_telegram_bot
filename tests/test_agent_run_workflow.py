from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    ProgressUpdated,
    ReplyReady,
    ToolExecutionRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.models.search import SearchWebResponse, SearchWebResult
from talking_telegram_bot.models.weather import WeatherForecastDay, WeatherResponse
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.conversation_lock_service import (
    ConversationLockService,
)
from talking_telegram_bot.handlers.weather_tool_handler import WeatherToolHandler
from talking_telegram_bot.workflows.agent_run_workflow import AgentRunWorkflow
from talking_telegram_bot.handlers.search_web_tool_handler import SearchWebToolHandler


class _EventCollector:
    def __init__(self) -> None:
        self.progress_texts: list[str] = []
        self.replies: list[str] = []
        self.errors: list[str] = []

    async def handle(self, envelope) -> None:
        if isinstance(envelope.message, ProgressUpdated):
            self.progress_texts.append(envelope.message.text)
        elif isinstance(envelope.message, ReplyReady):
            self.replies.append(envelope.message.text)
        elif isinstance(envelope.message, UserFacingErrorRaised):
            self.errors.append(envelope.message.text)


class AgentRunWorkflowTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_runs_search_tool_and_publishes_reply(self) -> None:
        event_bus = InMemoryEventBus(worker_count=4)
        response_service = AgentResponseService()
        agent_execution_service = AsyncMock()
        agent_execution_service.request_step.side_effect = [
            '{"thought":"need web data","action":"search_web","args":{"query":"latest ollama release"}}',
            '{"final_answer":"done with sources"}',
        ]
        search_web_service = AsyncMock()
        search_web_service.search_web.return_value = SearchWebResponse(
            query="latest ollama release",
            results=[
                SearchWebResult(
                    title="Release notes",
                    url="https://example.com/release",
                    content="Important changes",
                ),
            ],
        )
        collector = _EventCollector()
        event_bus.subscribe(
            AgentRunRequested,
            AgentRunWorkflow(
                agent_execution_service,
                response_service,
                event_bus,
                ConversationLockService(),
            ),
        )
        event_bus.subscribe(
            ToolExecutionRequested,
            SearchWebToolHandler(response_service, search_web_service, event_bus),
        )
        event_bus.subscribe(ProgressUpdated, collector)
        event_bus.subscribe(ReplyReady, collector)
        event_bus.subscribe(UserFacingErrorRaised, collector)

        await event_bus.publish_and_wait(
            AgentRunRequested(system_prompt="system", user_prompt="user task"),
            correlation_id="corr-3",
            user_id=123,
        )
        await asyncio.sleep(0.05)

        search_web_service.search_web.assert_awaited_once_with("latest ollama release")
        self.assertEqual(collector.replies, ["done with sources"])
        self.assertFalse(collector.errors)
        self.assertIn("Ищу в вебе...", collector.progress_texts)
        self.assertIn("Нашел результаты, формирую ответ...", collector.progress_texts)
        self.assertIn("Проверяю итог...", collector.progress_texts)
        await event_bus.stop()

    async def test_workflow_runs_weather_tool_and_publishes_reply(self) -> None:
        event_bus = InMemoryEventBus(worker_count=4)
        response_service = AgentResponseService()
        agent_execution_service = AsyncMock()
        agent_execution_service.request_step.side_effect = [
            '{"thought":"need weather","action":"weather","args":{"location":"London"}}',
            '{"final_answer":"done with weather"}',
        ]
        weather_service = AsyncMock()
        weather_service.get_weather.return_value = WeatherResponse(
            requested_location="London",
            resolved_location="London",
            region="England",
            country="United Kingdom",
            observation_time="2026-04-20 08:29 PM",
            condition="Patchy rain nearby",
            temp_c="12",
            temp_f="54",
            feels_like_c="11",
            feels_like_f="51",
            humidity="47",
            wind_speed_kmph="14",
            wind_speed_miles="9",
            wind_direction="NE",
            visibility_km="10",
            forecast=[
                WeatherForecastDay(
                    date="2026-04-20",
                    condition="Sunny",
                    min_temp_c="7",
                    max_temp_c="15",
                    min_temp_f="45",
                    max_temp_f="59",
                    sunrise="05:55 AM",
                    sunset="08:05 PM",
                ),
            ],
        )
        collector = _EventCollector()
        event_bus.subscribe(
            AgentRunRequested,
            AgentRunWorkflow(
                agent_execution_service,
                response_service,
                event_bus,
                ConversationLockService(),
            ),
        )
        event_bus.subscribe(
            ToolExecutionRequested,
            WeatherToolHandler(response_service, weather_service, event_bus),
        )
        event_bus.subscribe(ProgressUpdated, collector)
        event_bus.subscribe(ReplyReady, collector)
        event_bus.subscribe(UserFacingErrorRaised, collector)

        await event_bus.publish_and_wait(
            AgentRunRequested(system_prompt="system", user_prompt="weather task"),
            correlation_id="corr-5",
            user_id=123,
        )
        await asyncio.sleep(0.05)

        weather_service.get_weather.assert_awaited_once_with("London")
        self.assertEqual(collector.replies, ["done with weather"])
        self.assertFalse(collector.errors)
        self.assertIn("Проверяю погоду...", collector.progress_texts)
        self.assertIn("Проверяю итог...", collector.progress_texts)
        await event_bus.stop()
