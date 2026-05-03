from __future__ import annotations

import logging
from dataclasses import asdict

from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.user_messages import (
    WEB_RESULTS_PROGRESS_MESSAGE,
    WEB_SEARCH_PROGRESS_MESSAGE,
)
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.events import ProgressUpdated
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.agent_tool_dispatcher_service import (
    AgentToolContext,
    AgentToolExecutionError,
)
from talking_telegram_bot.services.search_web_service import (
    SearchWebService,
    SearchWebServiceError,
)

logger = logging.getLogger(__name__)


class SearchWebToolHandler:
    action_name = "search_web"

    def __init__(
        self,
        response_service: AgentResponseService,
        search_web_service: SearchWebService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._response_service = response_service
        self._search_web_service = search_web_service
        self._event_bus = event_bus

    async def execute(
        self,
        args: dict[str, object],
        context: AgentToolContext,
    ) -> str:
        query = args.get("query")
        if not isinstance(query, str):
            log_event(
                logger,
                logging.WARNING,
                log_events.AGENT_TOOL_FAILED,
                trace_id=context.correlation_id,
                chat_id=context.chat_id,
                user_id=context.user_id,
                tool_action=self.action_name,
                reason="invalid_query",
            )
            return self._response_service.build_error_observation(
                "Tool search_web requires a string query.",
            )
        await self._event_bus.publish(
            ProgressUpdated(text=WEB_SEARCH_PROGRESS_MESSAGE),
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            chat_id=context.chat_id,
            user_id=context.user_id,
        )
        try:
            search_response = await self._search_web_service.search_web(query)
        except SearchWebServiceError as exc:
            log_event(
                logger,
                logging.ERROR,
                log_events.AGENT_TOOL_FAILED,
                trace_id=context.correlation_id,
                chat_id=context.chat_id,
                user_id=context.user_id,
                tool_action=self.action_name,
                error=str(exc),
            )
            raise AgentToolExecutionError(str(exc)) from exc
        await self._event_bus.publish(
            ProgressUpdated(text=WEB_RESULTS_PROGRESS_MESSAGE),
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            chat_id=context.chat_id,
            user_id=context.user_id,
        )
        observation = self._response_service.build_tool_observation(
            self.action_name,
            {
                "query": search_response.query,
                "results": [asdict(result) for result in search_response.results],
            },
        )
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_TOOL_COMPLETED,
            trace_id=context.correlation_id,
            chat_id=context.chat_id,
            user_id=context.user_id,
            tool_action=self.action_name,
            result_count=len(search_response.results),
        )
        return observation
