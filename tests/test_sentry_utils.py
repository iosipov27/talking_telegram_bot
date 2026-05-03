from __future__ import annotations

import unittest

from talking_telegram_bot.logging_utils import logging_context
from talking_telegram_bot.sentry_utils import (
    SENTRY_CONTEXT_NAME,
    _add_request_context,
    configure_sentry,
)


class SentryUtilsTestCase(unittest.TestCase):
    def test_configure_sentry_skips_empty_dsn(self) -> None:
        self.assertFalse(configure_sentry(dsn=None, environment="test"))

    def test_before_send_adds_request_context_from_current_context(self) -> None:
        with logging_context(
            trace_id="trace-1",
            request_id="request-1",
            chat_id=10,
            user_id=20,
            envelope_id="message-1",
            causation_id="parent-1",
        ):
            event = _add_request_context({"extra": {}}, {})

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["tags"]["trace_id"], "trace-1")
        self.assertEqual(event["tags"]["request_id"], "request-1")
        self.assertEqual(event["user"], {"id": "20"})
        self.assertEqual(
            event["contexts"][SENTRY_CONTEXT_NAME],
            {
                "trace_id": "trace-1",
                "request_id": "request-1",
                "chat_id": 10,
                "user_id": 20,
                "envelope_id": "message-1",
                "causation_id": "parent-1",
            },
        )

    def test_before_send_prefers_event_extra_context(self) -> None:
        event = _add_request_context(
            {
                "extra": {
                    "trace_id": "trace-2",
                    "request_id": "request-2",
                    "chat_id": 30,
                    "user_id": 40,
                    "envelope_id": "message-2",
                    "causation_id": "parent-2",
                },
            },
            {},
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["tags"]["trace_id"], "trace-2")
        self.assertEqual(event["tags"]["request_id"], "request-2")
        self.assertEqual(event["user"], {"id": "40"})
        self.assertEqual(event["contexts"][SENTRY_CONTEXT_NAME]["chat_id"], 30)

    def test_before_send_adds_structured_json_log_extra(self) -> None:
        event = _add_request_context(
            {
                "level": "error",
                "logger": "talking_telegram_bot.tests",
                "timestamp": "2026-05-03T10:00:00Z",
                "logentry": {"formatted": "Example event"},
                "extra": {
                    "trace_id": "trace-3",
                    "request_id": "request-3",
                    "chat_id": 50,
                    "user_id": 60,
                    "service_name": "test-service",
                    "structured_fields": {"answer_count": 2},
                },
            },
            {},
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(
            event["extra"]["json_log"],
            {
                "level": "error",
                "message": "Example event",
                "service": "test-service",
                "trace_id": "trace-3",
                "request_id": "request-3",
                "timestamp": "2026-05-03T10:00:00Z",
                "chat_id": 50,
                "user_id": 60,
                "answer_count": 2,
            },
        )

    def test_before_send_redacts_telegram_bot_token_urls(self) -> None:
        event = _add_request_context(
            {
                "breadcrumbs": {
                    "values": [
                        {
                            "category": "httplib",
                            "data": {
                                "url": "https://api.telegram.org/bot123456:secret-token/getUpdates",
                            },
                        },
                    ],
                },
                "extra": {
                    "structured_fields": {
                        "url": "https://api.telegram.org/bot123456:secret-token/sendMessage",
                    },
                },
            },
            {},
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(
            event["breadcrumbs"]["values"][0]["data"]["url"],
            "https://api.telegram.org/bot[Filtered]/getUpdates",
        )
        self.assertEqual(
            event["extra"]["structured_fields"]["url"],
            "https://api.telegram.org/bot[Filtered]/sendMessage",
        )
        self.assertEqual(
            event["extra"]["json_log"]["url"],
            "https://api.telegram.org/bot[Filtered]/sendMessage",
        )
