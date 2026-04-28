from __future__ import annotations

from typing import Any

from ...utils.common import build_window_stats, floor_ts_to_hour, format_local_iso, safe_float

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ....Services.config.settings import SETTINGS as EXPORT_SETTINGS


class SHT30Processor:
    stream_name = "sht30"
    processor_name = "sht30_preprocessor"
    window_hours = (3, 6, 24, 72)
    short_trend_window_index = 1

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
    ) -> dict[str, Any]:
        record_payload: dict[str, Any] = source_record.payload
        packet_payload: dict[str, Any] = record_payload.get("packet", {}).get("sht30_data", {})
        sensor_payload: dict[str, Any] = record_payload.get("sensors", {}).get("sht30", {})

        sensor_id = str(packet_payload.get("sensor_id"))
        ts_server = source_record.ts_server
        ts_hour_bucket = source_record.ts_hour_bucket or floor_ts_to_hour(ts_server)
        local_iso = format_local_iso(ts_server, EXPORT_SETTINGS.timezone)
        bucket_local_iso = format_local_iso(ts_hour_bucket, EXPORT_SETTINGS.timezone)

        perception = {
            "temp_air_c": safe_float(packet_payload.get("sht_temp_c")),
            "humidity_air_pct": safe_float(packet_payload.get("sht_hum_pct")),
        }

        provisional_snapshot: dict[str, Any] = {
            "timestamps": {
                "ts_server": ts_server,
                "ts_hour_bucket": ts_hour_bucket,
            },
            "perception": perception,
        }
        windows = build_window_stats(
            records=history_records + [provisional_snapshot],
            observed_ts=ts_hour_bucket,
            metric_keys=("temp_air_c", "humidity_air_pct"),
            window_hours=self.window_hours,
        )

        short_temp_window_key = self._short_trend_window_key()
        temp_short_window = windows.get(short_temp_window_key, {}).get("temp_air_c", {})
        humidity_24h = windows.get("24h", {}).get("humidity_air_pct", {})

        quality = {
            "read_ok": bool(packet_payload.get("sht_read_ok", False)),
            "sample_valid": bool(packet_payload.get("sht_sample_valid", False)),
            "sensor_sample_valid": bool(sensor_payload.get("sample_valid", True)),
            "sample_interval_ms": packet_payload.get("sht_read_elapsed_ms"),
        }

        derived_signals: dict[str, Any] = {
            "temp_trend_window_key": short_temp_window_key,
            "temp_trend_short_horizon": temp_short_window.get("trend"),
            "temp_delta_short_horizon": temp_short_window.get("delta_from_start"),
            "humidity_trend_24h": humidity_24h.get("trend"),
            "humidity_delta_24h": humidity_24h.get("delta_from_start"),
            "humidity_avg_24h": humidity_24h.get("avg"),
        }

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
                "ts_hour_bucket": ts_hour_bucket,
                "observed_at_local": local_iso,
                "observed_at_hour_local": bucket_local_iso,
            },
            "perception": perception,
            "quality": quality,
            "memory": {
                "window_hours": list(self.window_hours),
                "windows": windows,
            },
            "context": {
                "hour_of_day": bucket_local_iso[11:13] if bucket_local_iso else None,
                "sample_interval_ms": packet_payload.get("sht_read_elapsed_ms"),
                "macro_humidity_trend_24h": humidity_24h.get("trend"),
                "temp_trend_window_key": short_temp_window_key,
            },
            "derived_signals": derived_signals,
        }

    def _short_trend_window_key(self) -> str:
        if not self.window_hours:
            return "24h"
        if len(self.window_hours) > self.short_trend_window_index:
            return f"{self.window_hours[self.short_trend_window_index]}h"
        return f"{self.window_hours[-1]}h"
