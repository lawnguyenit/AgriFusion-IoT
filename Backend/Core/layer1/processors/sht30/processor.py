from __future__ import annotations

from typing import Any

from ....utils.common import (
    build_window_stats,
    format_local_iso,
    safe_float,
)
from ...signals.fuzzy_signals import (
    compact_fuzzy_payload,
    evaluate_sht30_sample,
    previous_signals_from_history,
)

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from .....Services.config.settings import SETTINGS as EXPORT_SETTINGS


class SHT30Processor:
    stream_name = "sht30"
    processor_name = "sht30_preprocessor"
    window_hours = (3, 6, 24, 72)
    expected_interval_sec = 900
    max_regular_gap_sec = 1200
    boundary_tolerance_sec = 300
    metric_keys = ("temp_air_c", "humidity_air_pct")
    metric_aliases = {
        "temp_air_c": "temp",
        "humidity_air_pct": "humidity",
    }

    def extract_sensor_id(self, source_record: Any) -> str | None:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("sht30_data", {})
        sensor_id: Any = packet_payload.get("sensor_id")
        return str(sensor_id) if sensor_id else None

    def should_accept_source_record(self, source_record: Any) -> bool:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("sht30_data", {})
        sensor_payload: dict[str, Any] = source_record.payload.get("sensors", {}).get("sht30", {})
        required_metrics = ("sht_temp_c", "sht_hum_pct")

        if not packet_payload:
            return False
        if any(packet_payload.get(metric_key) is None for metric_key in required_metrics):
            return False
        if not bool(packet_payload.get("sht_read_ok", False)):
            return False
        if not bool(packet_payload.get("sht_sample_valid", False)):
            return False
        if sensor_payload and not bool(sensor_payload.get("sample_valid", True)):
            return False
        return True

    def build_snapshot(
        self,
        source_record: Any,
        history_records: list[dict[str, Any]],
        peer_histories: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        record_payload: dict[str, Any] = source_record.payload
        packet_payload: dict[str, Any] = record_payload.get("packet", {}).get("sht30_data", {})

        sensor_id = str(packet_payload.get("sensor_id"))
        ts_server = source_record.ts_server
        local_iso = format_local_iso(ts_server, EXPORT_SETTINGS.timezone)

        perception = {
            "temp_air_c": safe_float(packet_payload.get("sht_temp_c")),
            "humidity_air_pct": safe_float(packet_payload.get("sht_hum_pct")),
        }

        provisional_snapshot: dict[str, Any] = {
            "timestamps": {
                "ts_server": ts_server,
            },
            "perception": perception,
        }
        windows = build_window_stats(
            records=history_records + [provisional_snapshot],
            observed_ts=ts_server,
            metric_keys=self.metric_keys,
            window_hours=self.window_hours,
            expected_interval_sec=self.expected_interval_sec,
            max_regular_gap_sec=self.max_regular_gap_sec,
            boundary_tolerance_sec=self.boundary_tolerance_sec,
        )

        # quality = {
        #     "read_ok": bool(packet_payload.get("sht_read_ok", False)),
        #     "sample_valid": bool(packet_payload.get("sht_sample_valid", False)),
        #     "sensor_sample_valid": bool(sensor_payload.get("sample_valid", True)),
        #     "sample_interval_ms": packet_payload.get("sht_read_elapsed_ms"),
        # }

        fuzzy_signals = compact_fuzzy_payload(
            evaluate_sht30_sample(
                sample=provisional_snapshot,
                history=history_records,
                previous_signals=previous_signals_from_history(history_records),
            )
        )

        return {
            "schema_version": 1,
            "layer": "layer2",
            "processor_name": self.processor_name,
            "sensor_id": sensor_id,
            "sensor_type": packet_payload.get("sensor_type"),
            "source": {
                "event_key": source_record.event_key,
                "date_key": source_record.date_key,
                "path": source_record.source_path,
                "origin": source_record.source_kind,
                "source_name": source_record.source_name,
            },
            "timestamps": {
                "ts_device": source_record.ts_device,
                "ts_server": ts_server,
                "observed_at_local": local_iso,
            },
            "perception": perception,
            # "quality": quality,
            "memory": {
                "window_hours": list(self.window_hours),
                "expected_interval_sec": self.expected_interval_sec,
                "windows": windows,
            },
            "fuzzy_signals": fuzzy_signals,
        }
