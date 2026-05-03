from __future__ import annotations

import logging
from typing import Any

import httpx

from talking_telegram_bot.constants import log_events
from talking_telegram_bot.logging_utils import log_event
from talking_telegram_bot.models.messages import AssistantMessage, ConversationMessage

logger = logging.getLogger(__name__)
MAX_ERROR_RESPONSE_BODY_LENGTH = 4000


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
        self._timeout_seconds = timeout_seconds
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
            self._log_request_failed(
                "timeout",
                method="POST",
                endpoint="/api/chat",
            )
            raise OllamaTimeoutError("Ollama request failed: timeout.") from exc
        except httpx.HTTPStatusError as exc:
            reason = self._read_status_failure_reason(exc.response)
            self._log_request_failed(
                reason,
                method="POST",
                endpoint="/api/chat",
                status_code=exc.response.status_code,
                response_body=self._read_error_response_body(exc.response),
            )
            raise OllamaClientError(
                self._build_failure_message(reason, exc.response.status_code),
            ) from exc
        except httpx.ConnectError as exc:
            reason = self._read_connection_failure_reason(exc)
            self._log_request_failed(
                reason,
                method="POST",
                endpoint="/api/chat",
            )
            raise OllamaClientError(
                self._build_failure_message(reason),
            ) from exc
        except httpx.HTTPError as exc:
            self._log_request_failed(
                "http_error",
                method="POST",
                endpoint="/api/chat",
            )
            raise OllamaClientError("Ollama request failed: http error.") from exc
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
            self._log_request_failed(
                "timeout",
                method="GET",
                endpoint="/api/tags",
            )
            raise OllamaTimeoutError("Ollama request failed: timeout.") from exc
        except httpx.HTTPStatusError as exc:
            reason = self._read_status_failure_reason(exc.response)
            self._log_request_failed(
                reason,
                method="GET",
                endpoint="/api/tags",
                status_code=exc.response.status_code,
                response_body=self._read_error_response_body(exc.response),
            )
            raise OllamaClientError(
                self._build_failure_message(reason, exc.response.status_code),
            ) from exc
        except httpx.ConnectError as exc:
            reason = self._read_connection_failure_reason(exc)
            self._log_request_failed(
                reason,
                method="GET",
                endpoint="/api/tags",
            )
            raise OllamaClientError(
                self._build_failure_message(reason),
            ) from exc
        except httpx.HTTPError as exc:
            self._log_request_failed(
                "http_error",
                method="GET",
                endpoint="/api/tags",
            )
            raise OllamaClientError("Ollama request failed: http error.") from exc
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

    def _read_status_failure_reason(self, response: httpx.Response) -> str:
        body = self._read_error_response_body(response).lower()
        if response.status_code == 404 and "model" in body and "not found" in body:
            return "model_not_found"
        return "http_status"

    def _read_connection_failure_reason(self, error: httpx.ConnectError) -> str:
        message = str(error).lower()
        if "connection refused" in message or "connect call failed" in message:
            return "connection_refused"
        return "connection_error"

    def _read_error_response_body(self, response: httpx.Response) -> str:
        body = response.text
        if len(body) <= MAX_ERROR_RESPONSE_BODY_LENGTH:
            return body
        return f"{body[:MAX_ERROR_RESPONSE_BODY_LENGTH]}... [truncated]"

    def _build_failure_message(
        self,
        reason: str,
        status_code: int | None = None,
    ) -> str:
        readable_reason = reason.replace("_", " ")
        if status_code is not None and reason == "http_status":
            return f"Ollama request failed: HTTP {status_code}."
        return f"Ollama request failed: {readable_reason}."

    def _log_request_failed(
        self,
        reason: str,
        *,
        method: str,
        endpoint: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        fields: dict[str, object] = {
            "method": method,
            "endpoint": endpoint,
            "model": self._model,
            "reason": reason,
            "timeout_seconds": self._timeout_seconds,
        }
        if status_code is not None:
            fields["status_code"] = status_code
        if response_body is not None:
            fields["response_body"] = response_body
        log_event(
            logger,
            logging.ERROR,
            self._build_failure_message(reason, status_code),
            **fields,
            exc_info=True,
        )

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
