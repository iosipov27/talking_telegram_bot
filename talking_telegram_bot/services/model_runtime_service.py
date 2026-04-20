from __future__ import annotations

from dataclasses import dataclass

from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError


class ModelRuntimeError(RuntimeError):
    """Raised when the configured model can not be changed safely."""


@dataclass(frozen=True, slots=True)
class AvailableRuntimeModels:
    current_model: str
    model_names: list[str]


class ModelRuntimeService:
    def __init__(self, ollama_client: OllamaClient) -> None:
        self._ollama_client = ollama_client

    async def list_models(self) -> AvailableRuntimeModels:
        model_names = await self._load_model_names()
        return AvailableRuntimeModels(
            current_model=self._ollama_client.get_current_model(),
            model_names=model_names,
        )

    async def select_model_by_index(self, model_index: int) -> str:
        model_names = await self._load_model_names()
        if model_index < 0 or model_index >= len(model_names):
            raise ModelRuntimeError("Selected model index is not available.")
        selected_model = model_names[model_index]
        self._ollama_client.switch_model(selected_model)
        return selected_model

    async def _load_model_names(self) -> list[str]:
        try:
            model_names = await self._ollama_client.list_model_names()
        except OllamaClientError as exc:
            raise ModelRuntimeError("LLM model list is unavailable.") from exc
        if model_names:
            return model_names
        raise ModelRuntimeError("LLM returned an empty model list.")

