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

