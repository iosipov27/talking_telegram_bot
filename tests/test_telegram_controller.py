from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, call, patch

from talking_telegram_bot.constants.user_messages import (
    LLM_THINKING_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
    SAFE_MODEL_ERROR_MESSAGE,
)
from talking_telegram_bot.controllers.telegram_controller import (
    TelegramMessageController,
)
from talking_telegram_bot.services.model_service import AvailableModels, ModelSelectionError
from talking_telegram_bot.services.message_service import MessageProcessingError


class TelegramControllerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_handle_text_message_sends_service_reply(self) -> None:
        spinner_message = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
        message = SimpleNamespace(
            text="hi",
            reply_text=AsyncMock(return_value=spinner_message),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        service = AsyncMock()
        service.generate_reply.return_value = "hello"
        controller = TelegramMessageController(service, AsyncMock())

        await controller.handle_text_message(update, None)

        service.generate_reply.assert_awaited_once_with("hi", 123)
        message.reply_text.assert_has_awaits(
            [
                call(LLM_THINKING_MESSAGE.format(spinner="-")),
                call("hello"),
            ],
        )
        spinner_message.delete.assert_awaited_once()

    async def test_handle_text_message_sends_safe_error_message(self) -> None:
        spinner_message = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
        message = SimpleNamespace(
            text="hi",
            reply_text=AsyncMock(return_value=spinner_message),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        service = AsyncMock()
        service.generate_reply.side_effect = MessageProcessingError("down")
        controller = TelegramMessageController(service, AsyncMock())

        await controller.handle_text_message(update, None)

        message.reply_text.assert_has_awaits(
            [
                call(LLM_THINKING_MESSAGE.format(spinner="-")),
                call(SAFE_LLM_ERROR_MESSAGE),
            ],
        )
        spinner_message.delete.assert_awaited_once()

    async def test_handle_text_message_updates_thinking_spinner(self) -> None:
        reply_started = asyncio.Event()
        release_reply = asyncio.Event()
        spinner_message = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
        message = SimpleNamespace(
            text="hi",
            reply_text=AsyncMock(return_value=spinner_message),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        service = AsyncMock()
        service.generate_reply.side_effect = self._wait_for_reply(
            reply_started,
            release_reply,
        )
        controller = TelegramMessageController(service, AsyncMock())

        with patch(
            "talking_telegram_bot.controllers.telegram_controller."
            "SPINNER_UPDATE_SECONDS",
            0.01,
        ):
            task = asyncio.create_task(controller.handle_text_message(update, None))
            await reply_started.wait()
            await asyncio.sleep(0.03)
            release_reply.set()
            await task

        self.assertGreaterEqual(spinner_message.edit_text.await_count, 1)

    def _wait_for_reply(
        self,
        reply_started: asyncio.Event,
        release_reply: asyncio.Event,
    ):
        async def wait_for_reply(raw_text: str, user_id: int) -> str:
            del raw_text, user_id
            reply_started.set()
            await release_reply.wait()
            return "hello"

        return wait_for_reply

    async def test_handle_models_command_sends_model_keyboard(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        model_service = AsyncMock()
        model_service.list_models.return_value = AvailableModels(
            current_model="model-b",
            model_names=["model-a", "model-b"],
        )
        controller = TelegramMessageController(AsyncMock(), model_service)

        await controller.handle_models_command(update, None)

        message.reply_text.assert_awaited_once_with(
            text="Current Ollama model: model-b\nSelect a model:",
            reply_markup=ANY,
        )

    async def test_handle_models_command_sends_safe_error_message(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        model_service = AsyncMock()
        model_service.list_models.side_effect = ModelSelectionError("down")
        controller = TelegramMessageController(AsyncMock(), model_service)

        await controller.handle_models_command(update, None)

        message.reply_text.assert_awaited_once_with(SAFE_MODEL_ERROR_MESSAGE)

    async def test_handle_model_selection_edits_message_with_selected_model(self) -> None:
        query = SimpleNamespace(
            data="select_model:1",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        model_service = AsyncMock()
        model_service.select_model_by_index.return_value = "model-b"
        controller = TelegramMessageController(AsyncMock(), model_service)

        await controller.handle_model_selection(update, None)

        query.answer.assert_awaited_once()
        model_service.select_model_by_index.assert_awaited_once_with(1)
        query.edit_message_text.assert_awaited_once_with(
            "Current Ollama model: model-b",
        )
