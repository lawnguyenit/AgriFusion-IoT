from __future__ import annotations

from typing import Any

from ..Untils.common import build_window_stats, floor_ts_to_hour, format_local_iso, safe_float
from .meteo_health import assess_meteo_health

try:
    from Services.app_config import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ....Services.app_config import SETTINGS as EXPORT_SETTINGS

RAIN_EVENT_THRESHOLD_MM = 0.2
HEAT_STRESS_TEMP_C = 32.0
HIGH_HUMIDITY_PCT = 85.0


class MeteoProcessor:
    stream_name = "meteo"
    processor_name = "meteo_preprocessor"
    agent_name = "meteo_agent"
    window_hours = (3, 6, 24, 72)

    def extract_sensor_id(self, source_record: Any) -> str | None:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("meteo_data", {})
        sensor_id = packet_payload.get("sensor_id")
        return str(sensor_id) if sensor_id else None

    def build_snapshot(
        self,
        source_record: Any,
        history_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        record_payload: dict[str, Any] = source_record.payload
        packet_payload: dict[str, Any] = record_payload.get("packet", {}).get("meteo_data", {})
        sensor_payload: dict[str, Any] = record_payload.get("sensors", {}).get("meteo", {})
        health_payload: dict[str, Any] = record_payload.get("health", {}).get("meteo", {})

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
            "sensor_quality": safe_float(health_payload.get("quality") or sensor_payload.get("quality")),
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

        health = assess_meteo_health(packet_payload=packet_payload)
        if perception["sensor_quality"] is None:
            perception["sensor_quality"] = health["confidence"]

        temp_value = perception["temp_air_c"]
        humidity_value = perception["humidity_air_pct"]
        rain_value = perception["precipitation_mm"] or perception["rain_mm"]
        rain_24h = windows.get("24h", {}).get("precipitation_mm", {})
        humidity_24h = windows.get("24h", {}).get("humidity_air_pct", {})

        rain_event = bool(rain_value is not None and rain_value >= RAIN_EVENT_THRESHOLD_MM)
        heat_stress = bool(temp_value is not None and temp_value >= HEAT_STRESS_TEMP_C)
        humidity_alert = bool(humidity_value is not None and humidity_value >= HIGH_HUMIDITY_PCT)

        summary = "Weather stream is stable for downstream fusion."
        if health["status"] == "fault":
            summary = "Weather handoff confidence is low because key meteorology fields are missing."
        elif rain_event:
            summary = "Current weather indicates an active rainfall event."
        elif heat_stress:
            summary = "Ambient temperature is elevated for field operations."
        elif humidity_alert:
            summary = "Ambient humidity is high and may influence canopy microclimate."

        domain_signals: dict[str, Any] = {
            "rain_event": rain_event,
            "heat_stress": heat_stress,
            "humidity_alert": humidity_alert,
            "precipitation_delta_24h": rain_24h.get("delta_from_start"),
            "humidity_trend_24h": humidity_24h.get("trend"),
            "sensor_confidence": health["confidence"],
        }

        return {
            "schema_version": 1,
            "layer": "layer2",
            "processor_name": self.processor_name,
            "agent_name": self.agent_name,
            "sensor_id": sensor_id,
            "sensor_type": packet_payload.get("sensor_type"),
            "source": {
                "event_key": source_record.event_key,
                "date_key": source_record.date_key,
                "path": source_record.source_path,
                "origin": source_record.source_kind,
            },
            "timestamps": {
                "ts_device": source_record.ts_device,
                "ts_server": ts_server,
                "ts_hour_bucket": ts_hour_bucket,
                "observed_at_local": local_iso,
                "observed_at_hour_local": bucket_local_iso,
            },
            "perception": perception,
            "health": health,
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
            "inference_hints": {
                "status": health["status"],
                "summary": summary,
                "flags": {
                    "rain_event": rain_event,
                    "heat_stress": heat_stress,
                    "humidity_alert": humidity_alert,
                    "sensor_fault_possible": health["status"] == "fault",
                },
                "signals": domain_signals,
            },
            "layer3_interface": {
                "agent_name": self.agent_name,
                "timestamp": bucket_local_iso or local_iso,
                "status": health["status"],
                "confidence": health["confidence"],
                "severity": health["severity"],
                "summary": summary,
                "payload": domain_signals,
            },
            "handoff": {
                "target_layer": "layer3_domain_agent",
                "target_agent": self.agent_name,
                "ready": health["status"] != "fault",
                "reason": summary,
            },
        }
