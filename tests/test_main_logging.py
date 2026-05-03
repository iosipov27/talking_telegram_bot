from __future__ import annotations

import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

from talking_telegram_bot.logging_utils import JsonLogFormatter, MarkdownLogFormatter
from talking_telegram_bot.main import _configure_logging


class MainLoggingTestCase(unittest.TestCase):
    def test_configure_logging_uses_markdown_console_and_json_file(self) -> None:
        root_logger = logging.getLogger()
        old_handlers = list(root_logger.handlers)
        old_level = root_logger.level

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                _configure_logging(Path(temp_dir) / "bot.log")

                file_handlers = [
                    handler
                    for handler in root_logger.handlers
                    if isinstance(handler, RotatingFileHandler)
                ]
                console_handlers = [
                    handler
                    for handler in root_logger.handlers
                    if not isinstance(handler, RotatingFileHandler)
                ]

                self.assertEqual(len(console_handlers), 1)
                self.assertIsInstance(
                    console_handlers[0].formatter,
                    MarkdownLogFormatter,
                )
                self.assertEqual(len(file_handlers), 1)
                self.assertIsInstance(file_handlers[0].formatter, JsonLogFormatter)
            finally:
                for handler in root_logger.handlers:
                    handler.close()
                root_logger.handlers.clear()
                root_logger.handlers.extend(old_handlers)
                root_logger.setLevel(old_level)
