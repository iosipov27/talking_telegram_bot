from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from talking_telegram_bot.config.settings import SettingsError, load_settings


class SettingsTestCase(unittest.TestCase):
    def test_load_settings_disables_conversation_history_by_default(self) -> None:
        with patch.dict(os.environ, self._build_required_env(), clear=True):
            settings = load_settings()

        self.assertFalse(settings.conversation_history_enabled)

    def test_load_settings_enables_conversation_history_from_env(self) -> None:
        env = self._build_required_env()
        env["CONVERSATION_HISTORY_ENABLED"] = "true"
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()

        self.assertTrue(settings.conversation_history_enabled)

    def test_load_settings_rejects_invalid_conversation_history_flag(self) -> None:
        env = self._build_required_env()
        env["CONVERSATION_HISTORY_ENABLED"] = "maybe"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SettingsError):
                load_settings()

    def _build_required_env(self) -> dict[str, str]:
        return {
            "TELEGRAM_BOT_TOKEN": "token",
            "OLLAMA_BASE_URL": "http://ollama.local",
            "OLLAMA_MODEL": "test-model",
            "OLLAMA_TIMEOUT_SECONDS": "10",
            "TAVILY_API_KEY": "tavily-key",
        }
