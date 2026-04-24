from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.prompt_settings import AGENT_CONTINUE_PROMPT
from talking_telegram_bot.constants.user_messages import (
    FINAL_CHECK_PROGRESS_MESSAGE,
    WEATHER_LOOKUP_PROGRESS_MESSAGE,
    WEB_RESULTS_PROGRESS_MESSAGE,
    WEB_SEARCH_PROGRESS_MESSAGE,
)
from talking_telegram_bot.models.calculator import CalculatorResponse
from talking_telegram_bot.models.messages import AssistantMessage
from talking_telegram_bot.models.search import SearchWebResponse, SearchWebResult
from talking_telegram_bot.models.weather import WeatherForecastDay, WeatherResponse
from talking_telegram_bot.services.autonomous_agent_service import (
    AutonomousAgentError,
    AutonomousAgentService,
)


class AutonomousAgentServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_run_returns_final_answer_from_json(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(
            text='{"final_answer":"done"}',
        )
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        with patch.object(
            service,
            "_get_current_datetime_iso",
            return_value="2026-04-16T23:10:00+03:00",
        ):
            reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "done")
        request_messages = ollama_client.generate_reply.await_args.args[0]
        self.assertEqual(request_messages[1].role, "system")
        self.assertIn("2026-04-16T23:10:00+03:00", request_messages[1].content)

    async def test_run_returns_non_json_response_as_is(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(text="plain reply")
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "plain reply")

    async def test_run_extracts_final_answer_from_malformed_json(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(
            text='{"final_answer":"done"})',
        )
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "done")

    async def test_run_returns_final_response_from_action_payload(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(
            text='{"thought":"done","action":"final_response","args":{"response":"answer"}}',
        )
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "answer")

    async def test_run_returns_final_response_from_action_answer_payload(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(
            text='{"thought":"done","action":"final_response","args":{"answer":"answer"}}',
        )
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "answer")

    async def test_run_returns_final_response_from_top_level_response(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(
            text='{"thought":"done","action":"final_response","response":"answer"}',
        )
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "answer")

    async def test_run_executes_search_tool_and_continues(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(
                text='{"thought":"need web data","action":"search_web","args":{"query":"latest ollama release"}}',
            ),
            AssistantMessage(text='{"final_answer":"done with sources"}'),
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
        service = AutonomousAgentService(
            ollama_client,
            search_web_service,
            AsyncMock(),
        )

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "done with sources")
        search_web_service.search_web.assert_awaited_once_with("latest ollama release")
        second_call_messages = ollama_client.generate_reply.await_args_list[1].args[0]
        self.assertEqual(second_call_messages[3].role, "assistant")
        observation = json.loads(second_call_messages[4].content)
        self.assertEqual(observation["tool_name"], "search_web")
        self.assertEqual(observation["tool_result"]["query"], "latest ollama release")
        self.assertEqual(
            observation["tool_result"]["results"][0]["title"],
            "Release notes",
        )

    async def test_run_reports_web_progress_states(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(
                text='{"thought":"need web data","action":"search_web","args":{"query":"latest ollama release"}}',
            ),
            AssistantMessage(text='{"final_answer":"done with sources"}'),
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
        progress_callback = AsyncMock()
        service = AutonomousAgentService(
            ollama_client,
            search_web_service,
            AsyncMock(),
        )

        reply_text = await service.run(
            "system",
            "user task",
            progress_callback=progress_callback,
        )

        self.assertEqual(reply_text, "done with sources")
        progress_callback.assert_has_awaits(
            [
                call(WEB_SEARCH_PROGRESS_MESSAGE),
                call(WEB_RESULTS_PROGRESS_MESSAGE),
                call(FINAL_CHECK_PROGRESS_MESSAGE),
            ],
        )

    async def test_run_prompts_agent_to_continue_for_non_terminal_json(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(text='{"thought":"still thinking"}'),
            AssistantMessage(text='{"final_answer":"done"}'),
        ]
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "done")
        second_call_messages = ollama_client.generate_reply.await_args_list[1].args[0]
        self.assertEqual(second_call_messages[4].content, AGENT_CONTINUE_PROMPT)

    async def test_run_raises_after_too_many_steps(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.return_value = AssistantMessage(
            text='{"thought":"loop"}',
        )
        service = AutonomousAgentService(ollama_client, AsyncMock(), AsyncMock())

        with self.assertRaises(AutonomousAgentError):
            await service.run("system", "user task")

    async def test_run_logs_agent_thoughts(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(
                text='{"thought":"need web data","action":"search_web","args":{"query":"latest ollama release"}}',
            ),
            AssistantMessage(text='{"final_answer":"done"}'),
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
        service = AutonomousAgentService(
            ollama_client,
            search_web_service,
            AsyncMock(),
        )

        with self.assertLogs(
            "talking_telegram_bot.services.autonomous_agent_service",
            level="INFO",
        ) as logs:
            reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "done")
        log_output = "\n".join(logs.output)
        self.assertIn(log_events.AGENT_THOUGHT_RECEIVED, log_output)
        self.assertIn("| Step | 1 |", log_output)
        self.assertIn("| Action | search_web |", log_output)
        self.assertIn("| thought | need web data |", log_output)

    async def test_run_executes_calculator_tool_and_continues(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(
                text='{"thought":"need a calculation","action":"calculator","args":{"expression":"sqrt(2)"}}',
            ),
            AssistantMessage(text='{"final_answer":"done with math"}'),
        ]
        calculator_service = Mock()
        calculator_service.calculate.return_value = CalculatorResponse(
            expression="sqrt(2)",
            result="sqrt(2)",
            approximation="1.4142135623730951",
        )
        service = AutonomousAgentService(
            ollama_client,
            AsyncMock(),
            calculator_service,
        )

        reply_text = await service.run("system", "user task")

        self.assertEqual(reply_text, "done with math")
        calculator_service.calculate.assert_called_once_with("sqrt(2)")
        second_call_messages = ollama_client.generate_reply.await_args_list[1].args[0]
        observation = json.loads(second_call_messages[4].content)
        self.assertEqual(observation["tool_name"], "calculator")
        self.assertEqual(
            observation["tool_result"],
            {
                "expression": "sqrt(2)",
                "result": "sqrt(2)",
                "approximation": "1.4142135623730951",
            },
        )

    async def test_run_executes_weather_tool_and_continues(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.generate_reply.side_effect = [
            AssistantMessage(
                text='{"thought":"need weather","action":"weather","args":{"location":"London"}}',
            ),
            AssistantMessage(text='{"final_answer":"done with weather"}'),
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
        service = AutonomousAgentService(
            ollama_client,
            AsyncMock(),
            Mock(),
            weather_service,
        )
        progress_callback = AsyncMock()

        reply_text = await service.run(
            "system",
            "user task",
            progress_callback=progress_callback,
        )

        self.assertEqual(reply_text, "done with weather")
        weather_service.get_weather.assert_awaited_once_with("London")
        second_call_messages = ollama_client.generate_reply.await_args_list[1].args[0]
        observation = json.loads(second_call_messages[4].content)
        self.assertEqual(observation["tool_name"], "weather")
        self.assertEqual(observation["tool_result"]["resolved_location"], "London")
        progress_callback.assert_has_awaits(
            [
                call(WEATHER_LOOKUP_PROGRESS_MESSAGE),
                call(FINAL_CHECK_PROGRESS_MESSAGE),
            ],
        )
