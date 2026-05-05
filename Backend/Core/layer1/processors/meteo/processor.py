from __future__ import annotations

from typing import Any

from ....utils.common import (
    build_window_stats,
    format_local_iso,
    safe_float,
)
from ...signals.fuzzy_signals import (
    compact_fuzzy_payload,
    evaluate_meteo_sample,
    previous_signals_from_history,
)
from ...signals.external_weather import evaluate_external_weather

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from .....Services.config.settings import SETTINGS as EXPORT_SETTINGS


class MeteoProcessor:
    stream_name = "meteo"
    processor_name = "meteo_preprocessor"
    window_hours = (1, 3, 6, 24, 72)
    expected_interval_sec = 3600
    max_regular_gap_sec = 3900
    boundary_tolerance_sec = 300
    metric_keys = (
        "temp_air_c",
        "humidity_air_pct",
        "rain_mm",
        "precipitation_mm",
        "dew_point_c",
        "cloud_cover_pct",
        "soil_temp_0_7cm_c",
        "et0_mm",
    )
    metric_aliases = {
        "temp_air_c": "temp",
        "humidity_air_pct": "humidity",
        "rain_mm": "rain",
        "precipitation_mm": "precipitation",
        "dew_point_c": "dew_point",
        "cloud_cover_pct": "cloud_cover",
        "soil_temp_0_7cm_c": "soil_temp_0_7cm",
        "et0_mm": "et0",
    }

    def extract_sensor_id(self, source_record: Any) -> str | None:
        packet_payload: dict[str, Any] = source_record.payload.get("packet", {}).get("meteo_data", {})
        sensor_id = packet_payload.get("sensor_id")
        return str(sensor_id) if sensor_id else None

    def resolve_stream_name(self, source_record: Any) -> str:
        if source_record.source_name == "meteo_archive":
            return "meteo_archive_era5"
        if source_record.source_name == "meteo_forecast":
            return "meteo_forecast_ifs"
        return self.stream_name

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
        peer_histories: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        record_payload: dict[str, Any] = source_record.payload
        packet_payload: dict[str, Any] = record_payload.get("packet", {}).get("meteo_data", {})

        sensor_id = str(packet_payload.get("sensor_id"))
        ts_server = source_record.ts_server
        local_iso = format_local_iso(ts_server, EXPORT_SETTINGS.timezone)

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
        #     "core_temperature_present": packet_payload.get("temperature_2m") is not None,
        #     "core_humidity_present": packet_payload.get("relative_humidity_2m") is not None,
        #     "core_precipitation_present": (
        #         packet_payload.get("precipitation") is not None
        #         or packet_payload.get("rain") is not None
        #     ),
        #     "provider": record_payload.get("_meta_seed", {}).get("provider"),
        # }

        fuzzy_signals = compact_fuzzy_payload(
            evaluate_meteo_sample(
                sample=provisional_snapshot,
                history=history_records,
                previous_signals=previous_signals_from_history(history_records),
            )
        )
        external_weather = evaluate_external_weather(
            meteo_snapshot=provisional_snapshot,
            history_records=history_records,
            microclimate_records=(peer_histories or {}).get("sht30", []),
        )

        return {
            "schema_version": 1,
            "layer": "layer2",
            "processor_name": self.processor_name,
            "sensor_id": sensor_id,
            "sensor_type": packet_payload.get("sensor_type"),
            "source_mode": packet_payload.get("source_mode"),
            "provider": packet_payload.get("provider"),
            "model": packet_payload.get("model"),
            "is_observed_truth": packet_payload.get("is_observed_truth"),
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
            "external_weather": external_weather,
        }
