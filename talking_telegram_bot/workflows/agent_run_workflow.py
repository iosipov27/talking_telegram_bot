from __future__ import annotations

import asyncio
import logging

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.prompt_settings import AGENT_CONTINUE_PROMPT, AGENT_MAX_STEPS
from talking_telegram_bot.constants.user_messages import (
    FINAL_CHECK_PROGRESS_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
)
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.events import (
    AgentRunRequested,
    ProgressUpdated,
    ReplyReady,
    ResponseGenerated,
    ToolExecutionRequested,
    UserFacingErrorRaised,
)
from talking_telegram_bot.models.messages import ConversationMessage
from talking_telegram_bot.services.agent_execution_service import (
    AgentExecutionError,
    AgentExecutionService,
)
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.conversation_context_service import (
    ConversationContextError,
    ConversationContextService,
)
from talking_telegram_bot.services.conversation_lock_service import ConversationLockService

logger = logging.getLogger(__name__)


class AgentRunWorkflow:
    def __init__(
        self,
        agent_execution_service: AgentExecutionService,
        response_service: AgentResponseService,
        event_bus: InMemoryEventBus,
        conversation_lock_service: ConversationLockService,
        conversation_context_service: ConversationContextService | None = None,
    ) -> None:
        self._agent_execution_service = agent_execution_service
        self._response_service = response_service
        self._event_bus = event_bus
        self._conversation_lock_service = conversation_lock_service
        self._conversation_context_service = conversation_context_service

    async def handle(self, envelope: MessageEnvelope[AgentRunRequested]) -> None:
        if envelope.user_id is None:
            await self._publish_error(envelope)
            return
        async with self._conversation_lock_service.lock(envelope.user_id):
            try:
                reply_text = await self._run_agent(
                    envelope.message.system_prompt,
                    envelope.message.user_prompt,
                    envelope,
                )
            except AgentExecutionError as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "Agent workflow failed.",
                    trace_id=envelope.correlation_id,
                    chat_id=envelope.chat_id,
                    user_id=envelope.user_id,
                    error=str(exc),
                )
                await self._publish_error(envelope)
                return
            except Exception:
                log_event(
                    logger,
                    logging.ERROR,
                    "Unexpected agent workflow failure.",
                    trace_id=envelope.correlation_id,
                    chat_id=envelope.chat_id,
                    user_id=envelope.user_id,
                    exc_info=True,
                )
                await self._publish_error(envelope)
                return
        await self._event_bus.publish_and_wait(
            ResponseGenerated(text=reply_text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        await self._event_bus.publish_and_wait(
            ReplyReady(text=reply_text),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )

    async def _run_agent(
        self,
        system_prompt: str,
        user_prompt: str,
        envelope: MessageEnvelope[AgentRunRequested],
    ) -> str:
        context_messages = await self._read_context_messages(envelope)
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_RUN_REQUESTED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            context_message_count=len(context_messages),
        )
        messages = [
            ConversationMessage(role="system", content=system_prompt),
            *context_messages,
            ConversationMessage(role="user", content=user_prompt),
        ]
        for step_number in range(1, AGENT_MAX_STEPS + 1):
            if step_number > 1:
                await self._event_bus.publish(
                    ProgressUpdated(text=FINAL_CHECK_PROGRESS_MESSAGE),
                    correlation_id=envelope.correlation_id,
                    causation_id=envelope.message_id,
                    chat_id=envelope.chat_id,
                    user_id=envelope.user_id,
                )
            response_text = await self._agent_execution_service.request_step(messages)
            payload = self._response_service.parse_json_object(response_text)
            if payload is None:
                final_answer = self._response_service.read_final_answer_from_text(
                    response_text,
                )
                if final_answer is not None:
                    return final_answer
                return response_text
            self._log_thought(step_number, payload)
            final_answer = self._response_service.read_final_answer(payload)
            if final_answer is not None:
                return final_answer
            messages.append(ConversationMessage(role="assistant", content=response_text))
            messages.append(
                ConversationMessage(
                    role="user",
                    content=await self._build_follow_up(payload, envelope),
                ),
            )
        raise AgentExecutionError("Agent exceeded the maximum number of steps.")

    async def _build_follow_up(
        self,
        payload: dict[str, object],
        envelope: MessageEnvelope[AgentRunRequested],
    ) -> str:
        tool_call = self._response_service.read_tool_call(payload)
        if tool_call is None:
            return AGENT_CONTINUE_PROMPT
        if tool_call.action not in {"search_web", "calculator"}:
            log_event(
                logger,
                logging.WARNING,
                log_events.AGENT_TOOL_FAILED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                tool_action=tool_call.action,
                reason="unknown_tool",
            )
            return self._response_service.build_error_observation(
                f"Unknown tool: {tool_call.action}.",
            )
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_TOOL_REQUESTED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            tool_action=tool_call.action,
        )
        response_future = self._create_response_future()
        await self._event_bus.publish(
            ToolExecutionRequested(
                action=tool_call.action,
                args=tool_call.args,
                response_future=response_future,
            ),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        try:
            return await response_future
        except Exception as exc:
            raise AgentExecutionError(str(exc)) from exc

    def _create_response_future(self):
        return asyncio.get_running_loop().create_future()

    async def _read_context_messages(
        self,
        envelope: MessageEnvelope[AgentRunRequested],
    ) -> list[ConversationMessage]:
        if self._conversation_context_service is None or envelope.user_id is None:
            return []
        try:
            return await self._conversation_context_service.build_context_messages(
                envelope.user_id,
            )
        except ConversationContextError as exc:
            raise AgentExecutionError("Conversation context is unavailable.") from exc

    async def _publish_error(self, envelope: MessageEnvelope[AgentRunRequested]) -> None:
        await self._event_bus.publish_and_wait(
            ResponseGenerated(text=SAFE_LLM_ERROR_MESSAGE),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        await self._event_bus.publish_and_wait(
            UserFacingErrorRaised(text=SAFE_LLM_ERROR_MESSAGE),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )

    def _log_thought(self, step_number: int, payload: dict[str, object]) -> None:
        thought = payload.get("thought")
        if not isinstance(thought, str) or not thought.strip():
            return
        action = payload.get("action")
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_THOUGHT_RECEIVED,
            step=step_number,
            tool_action=action if isinstance(action, str) else None,
            thought_length=len(thought),
        )
