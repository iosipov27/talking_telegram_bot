from __future__ import annotations

import io
import json
import logging
import unittest

from talking_telegram_bot.logging_utils import (
    JsonLogFormatter,
    MarkdownLogFormatter,
    MarkdownTable,
    build_markdown_code_block,
    format_markdown_event,
    logging_context,
    logging_trace_context,
    log_event,
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

    def test_format_markdown_event_includes_code_blocks(self) -> None:
        formatted = format_markdown_event(
            "Example",
            [("Kind", "request")],
            detail_blocks=[
                build_markdown_code_block(
                    "Payload",
                    '{"ping": "pong"}',
                    language="json",
                ),
            ],
        )

        self.assertIn("#### Payload", formatted)
        self.assertIn("```json", formatted)
        self.assertIn('{"ping": "pong"}', formatted)

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

    def test_markdown_log_formatter_renders_event_as_console_ui(self) -> None:
        formatter = MarkdownLogFormatter(use_colors=True)
        record = logging.LogRecord(
            name="talking_telegram_bot.tests",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=format_markdown_event(
                "Telegram Reply",
                [("Text Length", 53)],
                detail_tables=[
                    MarkdownTable(
                        headers=("Role", "Content"),
                        rows=(("assistant", "LLM is unavailable."),),
                    ),
                ],
            ),
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        self.assertIn("Telegram Reply", formatted)
        self.assertIn("╭", formatted)
        self.assertIn("│", formatted)
        self.assertIn("assistant", formatted)
        self.assertNotIn("| Field | Value |", formatted)

    def test_markdown_log_formatter_renders_structured_log_event(self) -> None:
        formatter = MarkdownLogFormatter(use_colors=False)
        record = logging.LogRecord(
            name="talking_telegram_bot.tests",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Example event",
            args=(),
            exc_info=None,
        )
        record.trace_id = "trace-1"
        record.request_id = "request-1"
        record.chat_id = 10
        record.user_id = 20
        record.structured_fields = {"answer_count": 2}

        formatted = formatter.format(record)

        self.assertIn("### Example event", formatted)
        self.assertIn("| Trace ID | trace-1 |", formatted)
        self.assertIn("| Chat ID | 10 |", formatted)
        self.assertIn("| Answer Count | 2 |", formatted)

    def test_json_log_formatter_includes_required_fields(self) -> None:
        payload = self._capture_json_log(
            lambda logger: log_event(
                logger,
                logging.INFO,
                "Example event",
                trace_id="trace-1",
                service="test-service",
                answer_count=2,
            ),
        )

        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["message"], "Example event")
        self.assertEqual(payload["service"], "test-service")
        self.assertEqual(payload["trace_id"], "trace-1")
        self.assertEqual(payload["request_id"], "trace-1")
        self.assertEqual(payload["answer_count"], 2)
        self.assertIn("timestamp", payload)

    def test_json_log_formatter_serializes_exceptions(self) -> None:
        def write_error(logger: logging.Logger) -> None:
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                log_event(
                    logger,
                    logging.ERROR,
                    "Failure",
                    trace_id="trace-2",
                    exc_info=True,
                )

        payload = self._capture_json_log(write_error)

        self.assertEqual(payload["level"], "ERROR")
        self.assertEqual(payload["exception_type"], "RuntimeError")
        self.assertEqual(payload["exception_message"], "boom")
        self.assertIn("RuntimeError: boom", payload["exception_traceback"])

    def test_log_event_uses_trace_context(self) -> None:
        with logging_trace_context("trace-3"):
            payload = self._capture_json_log(
                lambda logger: log_event(logger, logging.DEBUG, "Context event"),
            )

        self.assertEqual(payload["trace_id"], "trace-3")
        self.assertEqual(payload["request_id"], "trace-3")

    def test_log_event_uses_request_context(self) -> None:
        with logging_context(
            trace_id="trace-4",
            request_id="request-4",
            chat_id=10,
            user_id=20,
            envelope_id="message-4",
            causation_id="parent-4",
        ):
            payload = self._capture_json_log(
                lambda logger: log_event(logger, logging.INFO, "Context event"),
            )

        self.assertEqual(payload["trace_id"], "trace-4")
        self.assertEqual(payload["request_id"], "request-4")
        self.assertEqual(payload["chat_id"], 10)
        self.assertEqual(payload["user_id"], 20)
        self.assertEqual(payload["envelope_id"], "message-4")
        self.assertEqual(payload["causation_id"], "parent-4")

    def test_log_event_defaults_to_system_trace(self) -> None:
        payload = self._capture_json_log(
            lambda logger: log_event(logger, logging.INFO, "Startup event"),
        )

        self.assertEqual(payload["trace_id"], "system")
        self.assertEqual(payload["request_id"], "system")

    def _capture_json_log(self, writer) -> dict[str, object]:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonLogFormatter())
        logger = logging.getLogger(f"{__name__}.{self._testMethodName}")
        old_level = logger.level
        old_propagate = logger.propagate
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        try:
            writer(logger)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            logger.propagate = old_propagate
        return json.loads(stream.getvalue())
