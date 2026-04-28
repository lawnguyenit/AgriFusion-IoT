from __future__ import annotations

from typing import Any

from ...utils.common import build_window_stats, floor_ts_to_hour, format_local_iso, safe_float

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ....Services.config.settings import SETTINGS as EXPORT_SETTINGS


class NPKProcessor:
    stream_name = "npk"
    processor_name = "npk_preprocessor"
    window_hours = (6, 24, 72)

    def extract_sensor_id(self, source_record: Any) -> str | None:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("npk_data", {})
        sensor_id = packet_payload.get("sensor_id")
        return str(sensor_id) if sensor_id else None

    def should_accept_source_record(self, source_record: Any) -> bool:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("npk_data", {})
        sensor_payload: dict[str, Any] = source_record.payload.get("sensors", {}).get("npk", {})
        required_metrics = ("N", "P", "K", "temp", "hum", "ph", "ec")

        if not packet_payload:
            return False
        if any(packet_payload.get(metric_key) is None for metric_key in required_metrics):
            return False
        if not bool(packet_payload.get("read_ok", False)):
            return False
        if not bool(packet_payload.get("npk_values_valid", False)):
            return False
        if packet_payload.get("frame_ok") is False:
            return False
        if packet_payload.get("crc_ok") is False:
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
        packet_payload: dict[str, Any] = record_payload.get("packet", {}).get("npk_data", {})
        sensor_payload: dict[str, Any] = record_payload.get("sensors", {}).get("npk", {})
        system_payload: dict[str, Any] = record_payload.get("packet", {}).get("system_data", {})

        sensor_id = str(packet_payload.get("sensor_id"))
        ts_server = source_record.ts_server
        ts_hour_bucket = source_record.ts_hour_bucket or floor_ts_to_hour(ts_server)
        local_iso = format_local_iso(ts_server, EXPORT_SETTINGS.timezone)
        bucket_local_iso = format_local_iso(ts_hour_bucket, EXPORT_SETTINGS.timezone)

        perception = {
            "n_ppm": safe_float(packet_payload.get("N")),
            "p_ppm": safe_float(packet_payload.get("P")),
            "k_ppm": safe_float(packet_payload.get("K")),
            "soil_temp_c": safe_float(packet_payload.get("temp")),
            "soil_humidity_pct": safe_float(packet_payload.get("hum")),
            "soil_ph": safe_float(packet_payload.get("ph")),
            "soil_ec_us_cm": safe_float(packet_payload.get("ec")),
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
            metric_keys=(
                "n_ppm",
                "p_ppm",
                "k_ppm",
                "soil_temp_c",
                "soil_humidity_pct",
                "soil_ph",
                "soil_ec_us_cm",
            ),
            window_hours=self.window_hours,
        )

        nutrient_values = [
            value
            for value in (
                perception["n_ppm"],
                perception["p_ppm"],
                perception["k_ppm"],
            )
            if value is not None
        ]
        nutrient_spread_ratio = None
        if nutrient_values:
            max_nutrient = max(nutrient_values)
            nutrient_spread_ratio = round(
                (max_nutrient - min(nutrient_values)) / max(max_nutrient, 1.0),
                4,
            )

        n_24h = windows.get("24h", {}).get("n_ppm", {})
        p_24h = windows.get("24h", {}).get("p_ppm", {})
        k_24h = windows.get("24h", {}).get("k_ppm", {})
        ph_24h = windows.get("24h", {}).get("soil_ph", {})
        ec_24h = windows.get("24h", {}).get("soil_ec_us_cm", {})
        moisture_24h = windows.get("24h", {}).get("soil_humidity_pct", {})

        quality = {
            "read_ok": bool(packet_payload.get("read_ok", False)),
            "frame_ok": packet_payload.get("frame_ok"),
            "crc_ok": packet_payload.get("crc_ok"),
            "values_valid": bool(packet_payload.get("npk_values_valid", False)),
            "sensor_alarm": bool(packet_payload.get("sensor_alarm", False)),
            "retry_count": packet_payload.get("retry_count"),
            "sensor_sample_valid": bool(sensor_payload.get("sample_valid", True)),
        }

        derived_signals: dict[str, Any] = {
            "nutrient_spread_ratio": nutrient_spread_ratio,
            "n_delta_24h": n_24h.get("delta_from_start"),
            "p_delta_24h": p_24h.get("delta_from_start"),
            "k_delta_24h": k_24h.get("delta_from_start"),
            "ph_delta_24h": ph_24h.get("delta_from_start"),
            "ec_delta_24h": ec_24h.get("delta_from_start"),
            "soil_moisture_trend_24h": moisture_24h.get("trend"),
            "soil_moisture_delta_24h": moisture_24h.get("delta_from_start"),
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
                "sample_interval_ms": packet_payload.get("sample_interval_ms"),
                "soil_moisture_trend_24h": moisture_24h.get("trend"),
                "transport": system_payload.get("transport"),
            },
            "derived_signals": derived_signals,
        }
