from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from talking_telegram_bot.clients.ollama_client import OllamaClientError
from talking_telegram_bot.services.model_service import ModelSelectionError, ModelService


class ModelServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_list_models_returns_current_model_and_available_models(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.get_current_model = Mock(return_value="model-a")
        ollama_client.list_model_names.return_value = ["model-a", "model-b"]
        service = ModelService(ollama_client)

        available_models = await service.list_models()

        self.assertEqual(available_models.current_model, "model-a")
        self.assertEqual(available_models.model_names, ["model-a", "model-b"])

    async def test_select_model_by_index_switches_client_model(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.switch_model = Mock()
        ollama_client.list_model_names.return_value = ["model-a", "model-b"]
        service = ModelService(ollama_client)

        selected_model = await service.select_model_by_index(1)

        self.assertEqual(selected_model, "model-b")
        ollama_client.switch_model.assert_called_once_with("model-b")

    async def test_select_model_by_index_rejects_unknown_index(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.list_model_names.return_value = ["model-a"]
        service = ModelService(ollama_client)

        with self.assertRaises(ModelSelectionError):
            await service.select_model_by_index(5)

    async def test_list_models_maps_client_errors(self) -> None:
        ollama_client = AsyncMock()
        ollama_client.list_model_names.side_effect = OllamaClientError("down")
        service = ModelService(ollama_client)

        with self.assertRaises(ModelSelectionError):
            await service.list_models()
