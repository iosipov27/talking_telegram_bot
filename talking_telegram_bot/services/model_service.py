from dataclasses import dataclass

from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError


class ModelSelectionError(RuntimeError):
    """Raised when the configured LLM model can not be changed safely."""


@dataclass(frozen=True)
class AvailableModels:
    current_model: str
    model_names: list[str]


class ModelService:
    def __init__(self, ollama_client: OllamaClient) -> None:
        self._ollama_client = ollama_client

    async def list_models(self) -> AvailableModels:
        model_names = await self._load_model_names()
        return AvailableModels(
            current_model=self._ollama_client.get_current_model(),
            model_names=model_names,
        )

    async def select_model_by_index(self, model_index: int) -> str:
        model_names = await self._load_model_names()
        if model_index < 0 or model_index >= len(model_names):
            raise ModelSelectionError("Selected model index is not available.")
        selected_model = model_names[model_index]
        self._ollama_client.switch_model(selected_model)
        return selected_model

    async def _load_model_names(self) -> list[str]:
        try:
            model_names = await self._ollama_client.list_model_names()
        except OllamaClientError as exc:
            raise ModelSelectionError("LLM model list is unavailable.") from exc
        if model_names:
            return model_names
        raise ModelSelectionError("LLM returned an empty model list.")
