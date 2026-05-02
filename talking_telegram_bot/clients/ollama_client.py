from __future__ import annotations

import logging
from typing import Any

import httpx

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.models.messages import AssistantMessage, ConversationMessage

logger = logging.getLogger(__name__)


class OllamaClientError(RuntimeError):
    """Raised when Ollama request or response handling fails."""


class OllamaTimeoutError(OllamaClientError):
    """Raised when Ollama does not respond in time."""


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def generate_reply(
        self,
        messages: list[ConversationMessage],
    ) -> AssistantMessage:
        payload = self._build_payload(messages)
        url = f"{self._base_url}/api/chat"
        log_event(
            logger,
            logging.INFO,
            log_events.OLLAMA_REQUEST_SENT,
            method="POST",
            endpoint="/api/chat",
            model=self._model,
            message_count=len(messages),
            stream=payload["stream"],
        )
        try:
            response = await self._http_client.post(
                url,
                json=payload,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaClientError("Ollama returned an unsuccessful status.") from exc
        except httpx.HTTPError as exc:
            raise OllamaClientError("Ollama request failed.") from exc
        assistant_message = AssistantMessage(
            text=self._extract_content(self._read_json(response)),
        )
        log_event(
            logger,
            logging.INFO,
            log_events.OLLAMA_RESPONSE_RECEIVED,
            model=self._model,
            content_length=len(assistant_message.text),
        )
        return assistant_message

    async def list_model_names(self) -> list[str]:
        url = f"{self._base_url}/api/tags"
        log_event(
            logger,
            logging.INFO,
            log_events.OLLAMA_MODEL_LIST_REQUEST_SENT,
            method="GET",
            endpoint="/api/tags",
        )
        try:
            response = await self._http_client.get(url)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama model list request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaClientError("Ollama returned an unsuccessful status.") from exc
        except httpx.HTTPError as exc:
            raise OllamaClientError("Ollama model list request failed.") from exc
        model_names = self._extract_model_names(self._read_json(response))
        log_event(
            logger,
            logging.INFO,
            log_events.OLLAMA_MODEL_LIST_RESPONSE_RECEIVED,
            model_count=len(model_names),
        )
        return model_names

    def get_current_model(self) -> str:
        return self._model

    def switch_model(self, model_name: str) -> None:
        self._model = model_name

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    def _build_payload(self, messages: list[ConversationMessage]) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "stream": False,
        }

    def _read_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise OllamaClientError("Ollama returned an invalid JSON payload.") from exc

    def _extract_content(self, data: Any) -> str:
        if not isinstance(data, dict):
            raise OllamaClientError("Ollama returned an invalid response payload.")
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaClientError("Ollama returned an invalid response payload.")
        content = message.get("content")
        if isinstance(content, str):
            return content
        raise OllamaClientError("Ollama returned an invalid response payload.")

    def _extract_model_names(self, data: Any) -> list[str]:
        if not isinstance(data, dict):
            raise OllamaClientError("Ollama returned an invalid response payload.")
        models = data.get("models")
        if not isinstance(models, list):
            raise OllamaClientError("Ollama returned an invalid response payload.")
        return self._read_names(models)

    def _read_names(self, models: list[Any]) -> list[str]:
        names = []
        for model in models:
            if not isinstance(model, dict):
                raise OllamaClientError("Ollama returned an invalid model payload.")
            name = model.get("name")
            if not isinstance(name, str) or not name:
                raise OllamaClientError("Ollama returned an invalid model name.")
            names.append(name)
        return sorted(names)
