from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from talking_telegram_bot.controllers.telegram_command_controller import (
    TelegramCommandController,
)
from talking_telegram_bot.messages.commands import ListModels, ShowRole, UpdateRole


class TelegramCommandControllerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_handle_models_command_dispatches_list_models(self) -> None:
        message = object()
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=10),
            effective_user=SimpleNamespace(id=20),
        )
        command_bus = AsyncMock()
        controller = TelegramCommandController(command_bus)

        await controller.handle_models_command(update, None)

        command_bus.execute.assert_awaited_once_with(
            ListModels(message=message),
            chat_id=10,
            user_id=20,
        )

    async def test_handle_role_command_without_args_dispatches_show_role(self) -> None:
        message = object()
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=10),
            effective_user=SimpleNamespace(id=20),
        )
        context = SimpleNamespace(args=[])
        command_bus = AsyncMock()
        controller = TelegramCommandController(command_bus)

        await controller.handle_role_command(update, context)

        command_bus.execute.assert_awaited_once_with(
            ShowRole(message=message),
            chat_id=10,
            user_id=20,
        )

    async def test_handle_role_command_with_args_dispatches_update_role(self) -> None:
        message = object()
        update = SimpleNamespace(
            effective_message=message,
            effective_chat=SimpleNamespace(id=10),
            effective_user=SimpleNamespace(id=20),
        )
        context = SimpleNamespace(args=["system", "analyst"])
        command_bus = AsyncMock()
        controller = TelegramCommandController(command_bus)

        await controller.handle_role_command(update, context)

        command_bus.execute.assert_awaited_once_with(
            UpdateRole(message=message, raw_role="system analyst"),
            chat_id=10,
            user_id=20,
        )
