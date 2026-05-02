from __future__ import annotations

import logging
from dataclasses import asdict

from talking_telegram_bot.bus.envelope import MessageEnvelope
from talking_telegram_bot.bus.event_bus import InMemoryEventBus
from talking_telegram_bot.constants import log_events
from talking_telegram_bot.constants.user_messages import (
    WEB_RESULTS_PROGRESS_MESSAGE,
    WEB_SEARCH_PROGRESS_MESSAGE,
)
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.messages.events import ProgressUpdated, ToolExecutionRequested
from talking_telegram_bot.services.agent_response_service import AgentResponseService
from talking_telegram_bot.services.search_web_service import (
    SearchWebService,
    SearchWebServiceError,
)

logger = logging.getLogger(__name__)


class SearchWebToolHandler:
    def __init__(
        self,
        response_service: AgentResponseService,
        search_web_service: SearchWebService,
        event_bus: InMemoryEventBus,
    ) -> None:
        self._response_service = response_service
        self._search_web_service = search_web_service
        self._event_bus = event_bus

    async def handle(self, envelope: MessageEnvelope[ToolExecutionRequested]) -> None:
        if envelope.message.action != "search_web":
            return
        if envelope.message.response_future.done():
            return
        query = envelope.message.args.get("query")
        if not isinstance(query, str):
            log_event(
                logger,
                logging.WARNING,
                log_events.AGENT_TOOL_FAILED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                tool_action=envelope.message.action,
                reason="invalid_query",
            )
            envelope.message.response_future.set_result(
                self._response_service.build_error_observation(
                    "Tool search_web requires a string query.",
                ),
            )
            return
        await self._event_bus.publish(
            ProgressUpdated(text=WEB_SEARCH_PROGRESS_MESSAGE),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        try:
            search_response = await self._search_web_service.search_web(query)
        except SearchWebServiceError as exc:
            log_event(
                logger,
                logging.ERROR,
                log_events.AGENT_TOOL_FAILED,
                trace_id=envelope.correlation_id,
                chat_id=envelope.chat_id,
                user_id=envelope.user_id,
                tool_action=envelope.message.action,
                error=str(exc),
            )
            envelope.message.response_future.set_exception(exc)
            return
        await self._event_bus.publish(
            ProgressUpdated(text=WEB_RESULTS_PROGRESS_MESSAGE),
            correlation_id=envelope.correlation_id,
            causation_id=envelope.message_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
        )
        envelope.message.response_future.set_result(
            self._response_service.build_tool_observation(
                envelope.message.action,
                {
                    "query": search_response.query,
                    "results": [asdict(result) for result in search_response.results],
                },
            ),
        )
        log_event(
            logger,
            logging.INFO,
            log_events.AGENT_TOOL_COMPLETED,
            trace_id=envelope.correlation_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            tool_action=envelope.message.action,
            result_count=len(search_response.results),
        )
