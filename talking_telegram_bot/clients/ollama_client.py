from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import (
    MarkdownTable,
    build_markdown_code_block,
    format_markdown_event,
)
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
        logger.info(self._format_chat_request_log(url, payload, messages))
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
        logger.info(self._format_response_log(assistant_message.text))
        return assistant_message

    async def list_model_names(self) -> list[str]:
        url = f"{self._base_url}/api/tags"
        logger.info(self._format_model_list_request_log(url))
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
        logger.info(self._format_model_list_response_log(model_names))
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

    def _format_chat_request_log(
        self,
        url: str,
        payload: dict[str, Any],
        messages: list[ConversationMessage],
    ) -> str:
        return format_markdown_event(
            log_events.OLLAMA_REQUEST_SENT,
            [
                ("Method", "POST"),
                ("URL", url),
                ("Model", self._model),
                ("Message Count", len(messages)),
                ("Stream", payload["stream"]),
            ],
            detail_tables=[
                MarkdownTable(
                    headers=("#", "Role", "Content"),
                    rows=tuple(
                        (index, message.role, message.content)
                        for index, message in enumerate(messages, start=1)
                    ),
                ),
            ],
            detail_blocks=[
                build_markdown_code_block(
                    "Raw Request JSON",
                    self._format_json(payload),
                    language="json",
                ),
            ],
        )

    def _format_response_log(self, content: str) -> str:
        return format_markdown_event(
            log_events.OLLAMA_RESPONSE_RECEIVED,
            [
                ("Model", self._model),
                ("Content Length", len(content)),
            ],
            detail_tables=[
                MarkdownTable(
                    headers=("Role", "Content"),
                    rows=(("assistant", content),),
                ),
            ],
        )

    def _format_model_list_request_log(self, url: str) -> str:
        return format_markdown_event(
            log_events.OLLAMA_MODEL_LIST_REQUEST_SENT,
            [
                ("Method", "GET"),
                ("URL", url),
            ],
        )

    def _format_model_list_response_log(self, model_names: list[str]) -> str:
        return format_markdown_event(
            log_events.OLLAMA_MODEL_LIST_RESPONSE_RECEIVED,
            [("Model Count", len(model_names))],
            detail_tables=[
                MarkdownTable(
                    headers=("#", "Model"),
                    rows=tuple(
                        (index, model_name)
                        for index, model_name in enumerate(model_names, start=1)
                    ),
                ),
            ],
        )

    def _format_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
