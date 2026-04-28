from __future__ import annotations

from typing import Any

from ...utils.common import build_window_stats, floor_ts_to_hour, format_local_iso, safe_float

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ....Services.config.settings import SETTINGS as EXPORT_SETTINGS


class MeteoProcessor:
    stream_name = "meteo"
    processor_name = "meteo_preprocessor"
    window_hours = (3, 6, 24, 72)

    def extract_sensor_id(self, source_record: Any) -> str | None:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("meteo_data", {})
        sensor_id = packet_payload.get("sensor_id")
        return str(sensor_id) if sensor_id else None

    def should_accept_source_record(self, source_record: Any) -> bool:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("meteo_data", {})
        if not packet_payload:
            return False
        if packet_payload.get("temperature_2m") is None:
            return False
        if packet_payload.get("relative_humidity_2m") is None:
            return False
        if packet_payload.get("precipitation") is None and packet_payload.get("rain") is None:
            return False
        return True

    def build_snapshot(
        self,
        source_record: Any,
        history_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        record_payload: dict[str, Any] = source_record.payload
        packet_payload: dict[str, Any] = record_payload.get("packet", {}).get("meteo_data", {})

        sensor_id = str(packet_payload.get("sensor_id"))
        ts_server = source_record.ts_server
        ts_hour_bucket = source_record.ts_hour_bucket or floor_ts_to_hour(ts_server)
        local_iso = format_local_iso(ts_server, EXPORT_SETTINGS.timezone)
        bucket_local_iso = format_local_iso(ts_hour_bucket, EXPORT_SETTINGS.timezone)

        perception: dict[str, Any] = {
            "temp_air_c": safe_float(packet_payload.get("temperature_2m")),
            "humidity_air_pct": safe_float(packet_payload.get("relative_humidity_2m")),
            "rain_mm": safe_float(packet_payload.get("rain")),
            "precipitation_mm": safe_float(packet_payload.get("precipitation")),
            "dew_point_c": safe_float(packet_payload.get("dew_point_2m")),
            "cloud_cover_pct": safe_float(packet_payload.get("cloud_cover")),
            "cloud_cover_high_pct": safe_float(packet_payload.get("cloud_cover_high")),
            "soil_temp_0_7cm_c": safe_float(packet_payload.get("soil_temperature_0_to_7cm")),
            "et0_mm": safe_float(packet_payload.get("et0_fao_evapotranspiration")),
            "weather_code": packet_payload.get("weather_code"),
            "is_day": packet_payload.get("is_day"),
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
                "temp_air_c",
                "humidity_air_pct",
                "rain_mm",
                "precipitation_mm",
                "dew_point_c",
                "cloud_cover_pct",
                "soil_temp_0_7cm_c",
                "et0_mm",
            ),
            window_hours=self.window_hours,
        )

        temp_24h = windows.get("24h", {}).get("temp_air_c", {})
        humidity_24h = windows.get("24h", {}).get("humidity_air_pct", {})
        precipitation_24h = windows.get("24h", {}).get("precipitation_mm", {})
        et0_24h = windows.get("24h", {}).get("et0_mm", {})

        quality = {
            "core_temperature_present": packet_payload.get("temperature_2m") is not None,
            "core_humidity_present": packet_payload.get("relative_humidity_2m") is not None,
            "core_precipitation_present": (
                packet_payload.get("precipitation") is not None
                or packet_payload.get("rain") is not None
            ),
            "provider": record_payload.get("_meta_seed", {}).get("provider"),
        }

        derived_signals: dict[str, Any] = {
            "temp_trend_24h": temp_24h.get("trend"),
            "temp_delta_24h": temp_24h.get("delta_from_start"),
            "humidity_trend_24h": humidity_24h.get("trend"),
            "humidity_delta_24h": humidity_24h.get("delta_from_start"),
            "precipitation_delta_24h": precipitation_24h.get("delta_from_start"),
            "et0_delta_24h": et0_24h.get("delta_from_start"),
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
                "is_day": packet_payload.get("is_day"),
                "weather_code": packet_payload.get("weather_code"),
                "timezone": packet_payload.get("timezone"),
                "provider": record_payload.get("_meta_seed", {}).get("provider"),
            },
            "derived_signals": derived_signals,
        }
