from __future__ import annotations

from typing import Any

import httpx

from talking_telegram_bot.models.messages import AssistantMessage, UserMessage


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

    async def generate_reply(self, user_message: UserMessage) -> AssistantMessage:
        payload = self._build_payload(user_message)
        try:
            response = await self._http_client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaClientError("Ollama returned an unsuccessful status.") from exc
        except httpx.HTTPError as exc:
            raise OllamaClientError("Ollama request failed.") from exc
        return AssistantMessage(text=self._extract_content(self._read_json(response)))

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    def _build_payload(self, user_message: UserMessage) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": user_message.text}],
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
