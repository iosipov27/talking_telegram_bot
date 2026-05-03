from __future__ import annotations

from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.models.messages import ConversationMessage
from talking_telegram_bot.services.agent_request_builder_service import (
    AgentRequestBuilderService,
)


class AgentExecutionError(RuntimeError):
    """Raised when an LLM step can not be completed safely."""


class AgentExecutionService:
    def __init__(
        self,
        ollama_client: OllamaClient,
        request_builder_service: AgentRequestBuilderService | None = None,
    ) -> None:
        self._ollama_client = ollama_client
        self._request_builder_service = (
            request_builder_service or AgentRequestBuilderService()
        )

    async def request_step(self, messages: list[ConversationMessage]) -> str:
        request_messages = self._request_builder_service.build_request_messages(messages)
        try:
            assistant_message = await self._ollama_client.generate_reply(request_messages)
        except OllamaClientError as exc:
            raise AgentExecutionError(str(exc)) from exc
        response_text = assistant_message.text.strip()
        if response_text:
            return response_text
        raise AgentExecutionError("LLM returned an empty response.")
