from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock, call, patch

from talking_telegram_bot.constants.user_messages import (
    FILE_READ_ERROR_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    LLM_THINKING_MESSAGE,
    ROLE_MESSAGE,
    ROLE_UPDATED_MESSAGE,
    SAFE_LLM_ERROR_MESSAGE,
    SAFE_MODEL_ERROR_MESSAGE,
    UNSUPPORTED_FILE_MESSAGE,
)
from talking_telegram_bot.controllers.telegram_controller import (
    TelegramMessageController,
)
from talking_telegram_bot.services.file_processing_service import (
    FileProcessingError,
    FileTooLargeError,
    UnsupportedFileTypeError,
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
        controller = TelegramMessageController(service, AsyncMock(), Mock())

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
        controller = TelegramMessageController(service, AsyncMock(), Mock())

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
        controller = TelegramMessageController(service, AsyncMock(), Mock())

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

    async def test_handle_text_message_logs_user_text_in_markdown_table(self) -> None:
        spinner_message = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
        message = SimpleNamespace(
            text="hello from telegram",
            reply_text=AsyncMock(return_value=spinner_message),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        service = AsyncMock()
        service.generate_reply.return_value = "hello"
        controller = TelegramMessageController(service, AsyncMock(), Mock())

        with self.assertLogs(
            "talking_telegram_bot.controllers.telegram_controller",
            level="INFO",
        ) as logs:
            await controller.handle_text_message(update, None)

        log_output = "\n".join(logs.output)
        self.assertIn("### Telegram Text Message", log_output)
        self.assertIn("| Role | Content |", log_output)
        self.assertIn("hello from telegram", log_output)

    async def test_handle_document_message_sends_service_reply(self) -> None:
        spinner_message = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
        telegram_file = SimpleNamespace(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"hello")),
        )
        document = SimpleNamespace(
            file_name="notes.txt",
            file_size=5,
            get_file=AsyncMock(return_value=telegram_file),
        )
        message = SimpleNamespace(
            document=document,
            reply_text=AsyncMock(return_value=spinner_message),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        message_service = AsyncMock()
        message_service.generate_reply.return_value = "summary"
        file_processing_service = Mock()
        file_processing_service.max_file_size_megabytes = 1
        file_processing_service.build_llm_prompt.return_value = "Analyze file"
        controller = TelegramMessageController(
            message_service,
            AsyncMock(),
            file_processing_service,
        )

        await controller.handle_document_message(update, None)

        file_processing_service.validate_metadata.assert_called_once_with(
            "notes.txt",
            5,
        )
        document.get_file.assert_awaited_once()
        telegram_file.download_as_bytearray.assert_awaited_once()
        file_processing_service.build_llm_prompt.assert_called_once_with(
            "notes.txt",
            b"hello",
        )
        message_service.generate_reply.assert_awaited_once_with("Analyze file", 123)
        message.reply_text.assert_has_awaits(
            [
                call(LLM_THINKING_MESSAGE.format(spinner="-")),
                call("summary"),
            ],
        )
        spinner_message.delete.assert_awaited_once()

    async def test_handle_document_message_rejects_unsupported_format(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        document = SimpleNamespace(file_name="image.png", file_size=5)
        message.document = document
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        message_service = AsyncMock()
        file_processing_service = Mock()
        file_processing_service.validate_metadata.side_effect = UnsupportedFileTypeError(
            "bad format",
        )
        file_processing_service.max_file_size_megabytes = 1
        controller = TelegramMessageController(
            message_service,
            AsyncMock(),
            file_processing_service,
        )

        await controller.handle_document_message(update, None)

        message.reply_text.assert_awaited_once_with(UNSUPPORTED_FILE_MESSAGE)
        message_service.generate_reply.assert_not_called()

    async def test_handle_document_message_rejects_large_file(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        document = SimpleNamespace(file_name="notes.txt", file_size=100)
        message.document = document
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        message_service = AsyncMock()
        file_processing_service = Mock()
        file_processing_service.validate_metadata.side_effect = FileTooLargeError(
            "too large",
        )
        file_processing_service.max_file_size_megabytes = 1
        controller = TelegramMessageController(
            message_service,
            AsyncMock(),
            file_processing_service,
        )

        await controller.handle_document_message(update, None)

        message.reply_text.assert_awaited_once_with(
            FILE_TOO_LARGE_MESSAGE.format(max_file_size_mb=1),
        )
        message_service.generate_reply.assert_not_called()

    async def test_handle_document_message_handles_unreadable_file(self) -> None:
        spinner_message = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
        telegram_file = SimpleNamespace(
            download_as_bytearray=AsyncMock(return_value=bytearray(b"\xff")),
        )
        document = SimpleNamespace(
            file_name="notes.txt",
            file_size=1,
            get_file=AsyncMock(return_value=telegram_file),
        )
        message = SimpleNamespace(
            document=document,
            reply_text=AsyncMock(return_value=spinner_message),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        message_service = AsyncMock()
        file_processing_service = Mock()
        file_processing_service.max_file_size_megabytes = 1
        file_processing_service.build_llm_prompt.side_effect = FileProcessingError(
            "bad encoding",
        )
        controller = TelegramMessageController(
            message_service,
            AsyncMock(),
            file_processing_service,
        )

        await controller.handle_document_message(update, None)

        message.reply_text.assert_has_awaits(
            [
                call(LLM_THINKING_MESSAGE.format(spinner="-")),
                call(FILE_READ_ERROR_MESSAGE),
            ],
        )
        message_service.generate_reply.assert_not_called()

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
        controller = TelegramMessageController(AsyncMock(), model_service, Mock())

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
        controller = TelegramMessageController(AsyncMock(), model_service, Mock())

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
        controller = TelegramMessageController(AsyncMock(), model_service, Mock())

        await controller.handle_model_selection(update, None)

        query.answer.assert_awaited_once()
        model_service.select_model_by_index.assert_awaited_once_with(1)
        query.edit_message_text.assert_awaited_once_with(
            "Current Ollama model: model-b",
        )

    async def test_handle_role_command_updates_agent_role(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        context = SimpleNamespace(args=["senior", "python", "developer"])
        message_service = Mock()
        message_service.update_agent_role = AsyncMock(
            return_value="senior python developer",
        )
        controller = TelegramMessageController(message_service, AsyncMock(), Mock())

        await controller.handle_role_command(update, context)

        message_service.update_agent_role.assert_awaited_once_with(
            "senior python developer",
            123,
        )
        message.reply_text.assert_awaited_once_with(
            ROLE_UPDATED_MESSAGE.format(agent_role="senior python developer"),
        )

    async def test_handle_role_command_without_args_shows_current_role(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=123),
        )
        context = SimpleNamespace(args=[])
        message_service = Mock()
        message_service.get_current_agent_role.return_value = "анонимный бот"
        controller = TelegramMessageController(message_service, AsyncMock(), Mock())

        await controller.handle_role_command(update, context)

        message.reply_text.assert_awaited_once_with(
            ROLE_MESSAGE.format(agent_role="анонимный бот"),
        )
