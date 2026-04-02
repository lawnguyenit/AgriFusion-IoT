from __future__ import annotations

from typing import Any

from ..Untils.common import build_window_stats, clamp, floor_ts_to_hour, format_local_iso, safe_float
from .SHT30_Health import assess_sht30_health

try:
    from Services.app_config import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ....Services.app_config import SETTINGS as EXPORT_SETTINGS

# Sensirion SHT30 nominal sensor capability is much tighter than our anomaly
# thresholds, so these are domain heuristics for downstream reasoning rather
# than hardware specs. They should be tuned with field data.
CONDENSATION_HUMIDITY_BASE_PCT = 85.0
CONDENSATION_TEMPERATURE_COOL_C = 26.0
HEAT_STRESS_TEMPERATURE_C = 31.0
AIR_STRESS_HUMIDITY_BASE_PCT = 80.0
HUMIDITY_SPIKE_DELTA_PCT = 7.5
WEATHER_SHIFT_REFERENCE_PCT = 12.0


class SHT30Processor:
    stream_name = "sht30"
    processor_name = "sht30_preprocessor"
    agent_name = "sht30_agent"
    window_hours = (3, 6, 24, 72)

    def extract_sensor_id(self, source_record: Any) -> str | None:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("sht30_data", {})
        sensor_id: Any = packet_payload.get("sensor_id")
        return str(sensor_id) if sensor_id else None

    def build_snapshot(
        self,
        source_record: Any,
        history_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Tạo ra đầu ra cuối cùng của layer2 cho một bản ghi nguồn và lịch sử (3, 6, 24, 72) giờ liên quan bao gồm:
            + Đánh giá sức khỏe cảm biến 
            + Các tín hiệu miền liên quan đến điều kiện không khí.

        Args:
            source_record (dict[str, Any]): _description_
            history_records (list[dict[str, Any]]): _description_

        Raises:
            heat: _description_

        Returns:
            dict[str, Any]: _description_
        """        
        record_payload: dict[str, Any] = source_record.payload
        packet_payload: dict[str, Any] = record_payload.get("packet", {}).get("sht30_data", {})
        sensor_payload = record_payload.get("sensors", {}).get("sht30", {})
        health_payload = record_payload.get("health", {}).get("sht30", {})
        overall_health = record_payload.get("health", {}).get("overall", {})
        system_payload = record_payload.get("packet", {}).get("system_data", {})

        sensor_id = str(packet_payload.get("sensor_id"))
        ts_server = source_record.ts_server
        ts_hour_bucket = source_record.ts_hour_bucket or floor_ts_to_hour(ts_server)
        local_iso = format_local_iso(ts_server, EXPORT_SETTINGS.timezone)
        bucket_local_iso = format_local_iso(ts_hour_bucket, EXPORT_SETTINGS.timezone)

        perception = {
            "temp_air_c": safe_float(packet_payload.get("sht_temp_c")),
            "humidity_air_pct": safe_float(packet_payload.get("sht_hum_pct")),
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
            metric_keys=("temp_air_c", "humidity_air_pct"),
            window_hours=self.window_hours,
        )

        health = assess_sht30_health(
            packet_payload=packet_payload,
            sensor_payload=sensor_payload,
            health_payload=health_payload,
            overall_health=overall_health,
        )

        temp_value = perception["temp_air_c"]
        temp_8h = windows.get("8h", {}).get("temp_air_c", {})
        humidity_value = perception["humidity_air_pct"]
        humidity_24h = windows.get("24h", {}).get("humidity_air_pct", {})

        condensation_risk = None
        if temp_value is not None and humidity_value is not None:
            condensation_risk = round(
                clamp(
                    ((humidity_value - CONDENSATION_HUMIDITY_BASE_PCT) / 15.0)
                    + max(0.0, (CONDENSATION_TEMPERATURE_COOL_C - temp_value) / 10.0)
                ),
                4,
            )

        air_stress_score = None
        if temp_value is not None and humidity_value is not None:
            air_stress_score = round(
                clamp(
                    max(0.0, (temp_value - (HEAT_STRESS_TEMPERATURE_C - 1.0)) / 8.0)
                    + max(0.0, (humidity_value - AIR_STRESS_HUMIDITY_BASE_PCT) / 20.0)
                ),
                4,
            )

        weather_driven_likelihood = None
        humidity_delta = humidity_24h.get("delta_from_start")

        # Lượng hoá trêh lệch độ ẩm với sự tự tin của cảm biến
        if humidity_delta is not None:
            weather_driven_likelihood = round(
                clamp((abs(humidity_delta) / WEATHER_SHIFT_REFERENCE_PCT) * max(0.35, health["confidence"])),
                4,
            )

        humidity_spike = bool(
            humidity_24h.get("avg") is not None
            and humidity_value is not None
            and abs(humidity_value - humidity_24h["avg"]) >= HUMIDITY_SPIKE_DELTA_PCT
        )
        heat_stress = bool(temp_value is not None and temp_value >= HEAT_STRESS_TEMPERATURE_C)
        condensation_alert = bool(condensation_risk is not None and condensation_risk >= 0.55)

        macro_humidity_trend = humidity_24h.get("trend")
        temp_trend_8h = temp_8h.get("trend")

        summary = "Air-climate stream is stable for the domain agent."
        if health["status"] == "fault":
            summary = "Air-climate handoff confidence is low because sensor reliability is degraded."
        elif condensation_alert:
            summary = "Humidity pattern suggests condensation risk."
        elif heat_stress:
            summary = "Air temperature is high enough to raise heat-stress attention."
        elif humidity_spike:
            summary = "Humidity deviates sharply from the recent baseline."

        domain_signals: dict[str, Any] = {
            "air_stress_score": air_stress_score,
            "weather_driven_likelihood": weather_driven_likelihood,
            "sensor_confidence": health["confidence"],
            "condensation_risk": condensation_risk,
            "macro_humidity_trend": macro_humidity_trend,
            "temp_trend_8h": temp_trend_8h,
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
                "sample_interval_ms": packet_payload.get("sht_read_elapsed_ms"),
                "macro_humidity_trend_24h": macro_humidity_trend,
                "transport": system_payload.get("transport"),
                "battery_v": overall_health.get("battery_v"),
            },
            "inference_hints": {
                "status": health["status"],
                "summary": summary,
                "flags": {
                    "humidity_spike": humidity_spike,
                    "condensation_risk": condensation_alert,
                    "heat_stress": heat_stress,
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
