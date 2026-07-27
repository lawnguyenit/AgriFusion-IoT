from __future__ import annotations

import unittest

from Backend.Core.layer1.contracts import SourceRecord
from Backend.Core.layer1.processors.common import normalize_buffer_reason
from Backend.Core.layer1.processors.context import (
    build_record_and_context_fields,
    extract_raw_buffer_reason,
)


class Layer1ContextProcessorTests(unittest.TestCase):
    def test_normalize_buffer_reason_collapses_verbose_raw_log(self) -> None:
        raw_reason = (
            "/Node1/telemetry/2026-07-01/123 -> http_action_fail | ok | "
            "*atready: 1 | +cpin: ready | sim: ready"
        )
        self.assertEqual(normalize_buffer_reason(raw_reason), "http_action_fail")

    def test_normalize_buffer_reason_distinguishes_auth_initialization(self) -> None:
        self.assertEqual(
            normalize_buffer_reason("publish_blocked_auth_not_initialized"),
            "auth_not_initialized",
        )

    def test_context_fields_keep_only_normalized_buffer_reason(self) -> None:
        raw_reason = (
            "/Node1/telemetry/2026-07-01/123 -> http_action_fail | ok | "
            "*atready: 1 | +cpin: ready"
        )
        source_record = SourceRecord(
            source_name="firebase",
            event_key="123",
            date_key="2026-07-01",
            source_kind="history",
            source_path="Node1/telemetry/2026-07-01/123",
            payload={
                "ts_sample": 1770001000,
                "ts_server": 1770001080,
                "buffer_reason": raw_reason,
                "replayed": True,
                "was_buffered": True,
                "event_meta": {"wake_reason": "timer"},
                "health": {"overall": {"online": True, "heap_free": 99}},
                "modules": {"sim": {"signal_dbm": -81, "gprs": True}},
                "packet": {"system_data": {"sample_epoch_sec": 1770001000}},
                "sensors": {},
            },
        )

        context_fields = build_record_and_context_fields(source_record)

        self.assertEqual(extract_raw_buffer_reason(source_record), raw_reason)
        self.assertEqual(context_fields["delivery.buffer_reason"], "http_action_fail")
        self.assertNotIn("delivery.buffer_reason_raw", context_fields)


if __name__ == "__main__":
    unittest.main()
