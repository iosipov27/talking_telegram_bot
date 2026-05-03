from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    ProgressUpdated,
    ReplyReady,
    UserFacingErrorRaised,
)
from talking_telegram_bot.models.search import SearchWebResponse, SearchWebResult
from talking_telegram_bot.constants.user_messages import SAFE_LLM_ERROR_MESSAGE
from talking_telegram_bot.models.messages import ConversationMessage
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.agent_execution_service import AgentExecutionError
from talking_telegram_bot.services.agent_tool_dispatcher_service import (
    AgentToolDispatcherService,
)
from talking_telegram_bot.services.conversation_lock_service import (
    ConversationLockService,
)
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


class _SlowTool:
    action_name = "slow_tool"

    async def execute(self, args, context) -> str:
        del args, context
        await asyncio.sleep(1)
        return "too late"


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
                AgentToolDispatcherService(
                    [
                        SearchWebToolHandler(
                            response_service,
                            search_web_service,
                            event_bus,
                        ),
                    ],
                ),
                event_bus,
                ConversationLockService(),
            ),
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

    async def test_workflow_runs_search_tool_from_json_with_trailing_garbage(
        self,
    ) -> None:
        event_bus = InMemoryEventBus(worker_count=4)
        response_service = AgentResponseService()
        agent_execution_service = AsyncMock()
        agent_execution_service.request_step.side_effect = [
            (
                '{"thought":"need web data","action":"search_web",'
                '"args":{"query":"лучшая рыба для ловли в озерах Румынии апрель 2026"}}}'
            ),
            '{"final_answer":"search complete"}',
        ]
        search_web_service = AsyncMock()
        search_web_service.search_web.return_value = SearchWebResponse(
            query="лучшая рыба для ловли в озерах Румынии апрель 2026",
            results=[
                SearchWebResult(
                    title="Fishing",
                    url="https://example.com/fishing",
                    content="Details",
                ),
            ],
        )
        collector = _EventCollector()
        event_bus.subscribe(
            AgentRunRequested,
            AgentRunWorkflow(
                agent_execution_service,
                response_service,
                AgentToolDispatcherService(
                    [
                        SearchWebToolHandler(
                            response_service,
                            search_web_service,
                            event_bus,
                        ),
                    ],
                ),
                event_bus,
                ConversationLockService(),
            ),
        )
        event_bus.subscribe(ReplyReady, collector)

        await event_bus.publish_and_wait(
            AgentRunRequested(system_prompt="system", user_prompt="user task"),
            correlation_id="corr-9",
            user_id=123,
        )
        await asyncio.sleep(0.05)

        search_web_service.search_web.assert_awaited_once_with(
            "лучшая рыба для ловли в озерах Румынии апрель 2026",
        )
        self.assertEqual(collector.replies, ["search complete"])
        await event_bus.stop()

    async def test_workflow_logs_expected_agent_failure_as_error(self) -> None:
        event_bus = InMemoryEventBus(worker_count=4)
        response_service = AgentResponseService()
        agent_execution_service = AsyncMock()
        agent_execution_service.request_step.side_effect = AgentExecutionError(
            "Ollama request failed: timeout.",
        )
        collector = _EventCollector()
        event_bus.subscribe(
            AgentRunRequested,
            AgentRunWorkflow(
                agent_execution_service,
                response_service,
                AgentToolDispatcherService([]),
                event_bus,
                ConversationLockService(),
            ),
        )
        event_bus.subscribe(UserFacingErrorRaised, collector)

        with self.assertLogs(
            "talking_telegram_bot.workflows.agent_run_workflow",
            level="ERROR",
        ) as logs:
            await event_bus.publish_and_wait(
                AgentRunRequested(system_prompt="system", user_prompt="user task"),
                correlation_id="corr-6",
                user_id=123,
            )
            await asyncio.sleep(0.05)

        self.assertEqual(collector.errors, [SAFE_LLM_ERROR_MESSAGE])
        self.assertIn("Ollama request failed: timeout.", "\n".join(logs.output))
        await event_bus.stop()

    async def test_workflow_fails_safely_when_tool_times_out(self) -> None:
        event_bus = InMemoryEventBus(worker_count=4)
        response_service = AgentResponseService()
        agent_execution_service = AsyncMock()
        agent_execution_service.request_step.return_value = (
            '{"thought":"needs slow tool","action":"slow_tool","args":{}}'
        )
        collector = _EventCollector()
        event_bus.subscribe(
            AgentRunRequested,
            AgentRunWorkflow(
                agent_execution_service,
                response_service,
                AgentToolDispatcherService([_SlowTool()], timeout_seconds=0.01),
                event_bus,
                ConversationLockService(),
            ),
        )
        event_bus.subscribe(UserFacingErrorRaised, collector)

        with self.assertLogs(
            "talking_telegram_bot.workflows.agent_run_workflow",
            level="ERROR",
        ):
            await event_bus.publish_and_wait(
                AgentRunRequested(system_prompt="system", user_prompt="user task"),
                correlation_id="corr-timeout",
                user_id=123,
            )
            await asyncio.sleep(0.05)

        self.assertEqual(collector.errors, [SAFE_LLM_ERROR_MESSAGE])
        await event_bus.stop()

    async def test_workflow_sends_saved_context_to_agent(self) -> None:
        event_bus = InMemoryEventBus(worker_count=4)
        response_service = AgentResponseService()
        agent_execution_service = AsyncMock()
        agent_execution_service.request_step.return_value = '{"final_answer":"ok"}'
        conversation_context_service = AsyncMock()
        conversation_context_service.build_context_messages.return_value = [
            ConversationMessage(role="system", content="remembered summary"),
            ConversationMessage(role="user", content="old request"),
            ConversationMessage(role="assistant", content="old response"),
        ]
        event_bus.subscribe(
            AgentRunRequested,
            AgentRunWorkflow(
                agent_execution_service,
                response_service,
                AgentToolDispatcherService([]),
                event_bus,
                ConversationLockService(),
                conversation_context_service,
            ),
        )

        await event_bus.publish_and_wait(
            AgentRunRequested(system_prompt="system", user_prompt="new request"),
            correlation_id="corr-7",
            user_id=123,
        )
        await asyncio.sleep(0.05)

        agent_execution_service.request_step.assert_awaited_once_with(
            [
                ConversationMessage(role="system", content="system"),
                ConversationMessage(role="system", content="remembered summary"),
                ConversationMessage(role="user", content="old request"),
                ConversationMessage(role="assistant", content="old response"),
                ConversationMessage(role="user", content="new request"),
            ],
        )
        await event_bus.stop()

    async def test_workflow_extracts_final_answer_from_malformed_json(self) -> None:
        event_bus = InMemoryEventBus(worker_count=4)
        response_service = AgentResponseService()
        agent_execution_service = AsyncMock()
        agent_execution_service.request_step.return_value = (
            '{"final_answer":"Привет!!! Сегодня пятница, 25 апреля 2026 года."})'
        )
        collector = _EventCollector()
        event_bus.subscribe(
            AgentRunRequested,
            AgentRunWorkflow(
                agent_execution_service,
                response_service,
                AgentToolDispatcherService([]),
                event_bus,
                ConversationLockService(),
            ),
        )
        event_bus.subscribe(ReplyReady, collector)

        await event_bus.publish_and_wait(
            AgentRunRequested(system_prompt="system", user_prompt="hello"),
            correlation_id="corr-8",
            user_id=123,
        )
        await asyncio.sleep(0.05)

        self.assertEqual(
            collector.replies,
            ["Привет!!! Сегодня пятница, 25 апреля 2026 года."],
        )
        await event_bus.stop()
