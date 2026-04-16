from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from talking_telegram_bot.constants.prompt_settings import AGENT_SYSTEM_PROMPT
from talking_telegram_bot.services.autonomous_agent_service import AutonomousAgentError
from talking_telegram_bot.services.message_service import (
    AgentRoleSelectionError,
    MessageProcessingError,
    MessageService,
)


class MessageServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_generate_reply_returns_trimmed_text(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = "  hello  "
        service = MessageService(agent_service)

        reply_text = await service.generate_reply("  hi  ", 123)

        self.assertEqual(reply_text, "hello")

    async def test_generate_reply_builds_system_prompt_once_per_request(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = "hello"
        service = MessageService(agent_service)

        await service.generate_reply("  hi  ", 123)

        agent_service.run.assert_awaited_once_with(
            AGENT_SYSTEM_PROMPT.format(agent_role="autonomous AI agent"),
            "hi",
        )

    async def test_generate_reply_uses_updated_agent_role(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = "hello"
        service = MessageService(agent_service)
        service.set_agent_role("системный аналитик")

        await service.generate_reply("hi", 123)

        agent_service.run.assert_awaited_once_with(
            AGENT_SYSTEM_PROMPT.format(agent_role="системный аналитик"),
            "hi",
        )

    async def test_generate_reply_raises_for_empty_input(self) -> None:
        service = MessageService(AsyncMock())

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("   ", 123)

    async def test_generate_reply_raises_for_empty_llm_output(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = "   "
        service = MessageService(agent_service)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    async def test_generate_reply_returns_final_response_from_json_payload(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = (
            '{"action":"final_response","args":{"response":"done"}}'
        )
        service = MessageService(agent_service)

        reply_text = await service.generate_reply("hi", 123)

        self.assertEqual(reply_text, "done")

    async def test_generate_reply_returns_final_answer_from_json_answer_payload(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = (
            '{"action":"final_response","args":{"answer":"done"}}'
        )
        service = MessageService(agent_service)

        reply_text = await service.generate_reply("hi", 123)

        self.assertEqual(reply_text, "done")

    async def test_generate_reply_returns_top_level_final_response(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = (
            '{"thought":"ready","action":"final_response","response":"done"}'
        )
        service = MessageService(agent_service)

        reply_text = await service.generate_reply("hi", 123)

        self.assertEqual(reply_text, "done")

    async def test_generate_reply_formats_json_object_as_table(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.return_value = (
            '{"thought":"need summary","action":"inspect","args":{"filename":"bot.txt","file_read":true}}'
        )
        service = MessageService(agent_service)

        reply_text = await service.generate_reply("hi", 123)

        self.assertIn("| Field | Value |", reply_text)
        self.assertIn("| thought | need summary |", reply_text)
        self.assertIn("| action | inspect |", reply_text)
        self.assertIn("| args.filename | bot.txt |", reply_text)
        self.assertIn("| args.file_read | true |", reply_text)

    async def test_generate_reply_maps_agent_failures(self) -> None:
        agent_service = AsyncMock()
        agent_service.run.side_effect = AutonomousAgentError("down")
        service = MessageService(agent_service)

        with self.assertRaises(MessageProcessingError):
            await service.generate_reply("hi", 123)

    def test_set_agent_role_normalizes_role_wrapper(self) -> None:
        service = MessageService(AsyncMock())

        selected_role = service.set_agent_role("  <role>Ты системный аналитик</role>  ")

        self.assertEqual(selected_role, "системный аналитик")

    async def test_update_agent_role_returns_selected_role(self) -> None:
        service = MessageService(AsyncMock())

        selected_role = await service.update_agent_role("историк", 123)

        self.assertEqual(selected_role, "историк")
        self.assertEqual(service.get_current_agent_role(), "историк")

    def test_set_agent_role_raises_for_empty_role(self) -> None:
        service = MessageService(AsyncMock())

        with self.assertRaises(AgentRoleSelectionError):
            service.set_agent_role("   ")
