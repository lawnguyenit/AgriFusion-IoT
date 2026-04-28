from __future__ import annotations

from typing import Any

from ...utils.common import build_window_stats, clamp, floor_ts_to_hour, format_local_iso, safe_float
from .health import assess_npk_health

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ....Services.config.settings import SETTINGS as EXPORT_SETTINGS

# These thresholds are agronomic/domain heuristics, not vendor guarantees.
# They should be field-calibrated against local crop/soil conditions.
SALINITY_RISK_BASELINE_US_CM = 1200.0
HIGH_SOIL_MOISTURE_PCT = 75.0
LOW_PH_BOUND = 5.5
HIGH_PH_BOUND = 7.4
NUTRIENT_IMBALANCE_INDEX = 0.55
LEACHING_N_SHIFT_DELTA = -8.0


class NPKProcessor:
    stream_name = "npk"
    processor_name = "npk_preprocessor"
    agent_name = "npk_agent"
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
        health_payload: dict[str, Any] = record_payload.get("health", {}).get("npk", {})
        overall_health: dict[str, Any] = record_payload.get("health", {}).get("overall", {})
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

        health = assess_npk_health(
            packet_payload=packet_payload,
            sensor_payload=sensor_payload,
            health_payload=health_payload,
            overall_health=overall_health,
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
        nutrient_balance_index = None
        if nutrient_values:
            max_nutrient = max(nutrient_values)
            nutrient_balance_index = round(
                (max_nutrient - min(nutrient_values)) / max(max_nutrient, 1.0),
                4,
            )

        ph_value = perception["soil_ph"]
        ec_value = perception["soil_ec_us_cm"]
        humidity_value = perception["soil_humidity_pct"]

        nutrient_shift = windows.get("24h", {}).get("n_ppm", {}).get("delta_from_start")
        ph_shift = windows.get("24h", {}).get("soil_ph", {}).get("delta_from_start")
        moisture_trend = windows.get("24h", {}).get("soil_humidity_pct", {}).get("trend")

        salinity_risk = None
        if ec_value is not None:
            salinity_risk = round(
                clamp((ec_value - SALINITY_RISK_BASELINE_US_CM) / SALINITY_RISK_BASELINE_US_CM),
                4,
            )

        ph_out_of_band = bool(ph_value is not None and (ph_value < LOW_PH_BOUND or ph_value > HIGH_PH_BOUND))
        high_moisture = bool(humidity_value is not None and humidity_value >= HIGH_SOIL_MOISTURE_PCT)
        nutrient_imbalance = bool(
            nutrient_balance_index is not None and nutrient_balance_index >= NUTRIENT_IMBALANCE_INDEX
        )
        possible_leaching = bool(
            high_moisture
            and nutrient_shift is not None
            and nutrient_shift < LEACHING_N_SHIFT_DELTA
        )
        dry_soil_reliability_risk = bool(health.get("evidence", {}).get("dry_soil_risk"))

        summary = "Soil chemistry is stable for domain inference."
        if health["status"] == "fault":
            summary = "NPK handoff confidence is low because sensor reliability is degraded."
        elif dry_soil_reliability_risk:
            summary = "Dry soil is reducing trust in the NPK reading."
        elif ph_out_of_band:
            summary = "Soil pH is outside the nominal operating band."
        elif possible_leaching:
            summary = "Moisture and nutrient shift suggest possible nutrient leaching."
        elif nutrient_imbalance:
            summary = "NPK ratio is imbalanced and should be reviewed by the domain agent."

        domain_signals: dict[str, Any] = {
            "nutrient_balance_index": nutrient_balance_index,
            "salinity_risk": salinity_risk,
            "ph_out_of_band": ph_out_of_band,
            "ph_shift_24h": ph_shift,
            "possible_leaching": possible_leaching,
            "dry_soil_reliability_risk": dry_soil_reliability_risk,
            "soil_moisture_trend": moisture_trend,
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
                "sample_interval_ms": packet_payload.get("sample_interval_ms"),
                "soil_moisture_trend_24h": moisture_trend,
                "transport": system_payload.get("transport"),
                "battery_v": overall_health.get("battery_v"),
            },
            "inference_hints": {
                "status": health["status"],
                "summary": summary,
                "flags": {
                    "nutrient_imbalance": nutrient_imbalance,
                    "possible_leaching": possible_leaching,
                    "ph_out_of_band": ph_out_of_band,
                    "dry_soil_reliability_risk": dry_soil_reliability_risk,
                    "salinity_risk_high": bool(salinity_risk is not None and salinity_risk >= 0.5),
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
