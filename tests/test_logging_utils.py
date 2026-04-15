from __future__ import annotations

import logging
import unittest

from talking_telegram_bot.logging_utils import (
    MarkdownLogFormatter,
    MarkdownTable,
    format_markdown_event,
)


class LoggingUtilsTestCase(unittest.TestCase):
    def test_format_markdown_event_builds_tables(self) -> None:
        formatted = format_markdown_event(
            "Example",
            [("Text", "hello | world"), ("Lines", "one\ntwo")],
            detail_tables=[
                MarkdownTable(
                    headers=("Role", "Content"),
                    rows=(("user", "ping"),),
                ),
            ],
        )

        self.assertIn("### Example", formatted)
        self.assertIn("| Field | Value |", formatted)
        self.assertIn("hello \\| world", formatted)
        self.assertIn("one<br>two", formatted)
        self.assertIn("| Role | Content |", formatted)

    def test_markdown_log_formatter_adds_color_header(self) -> None:
        formatter = MarkdownLogFormatter(use_colors=True)
        record = logging.LogRecord(
            name="talking_telegram_bot.tests",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        self.assertIn("\033[36m[INFO]", formatted)
        self.assertIn("talking_telegram_bot.tests", formatted)
        self.assertTrue(formatted.endswith("\nhello"))
