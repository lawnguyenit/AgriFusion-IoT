"""Adapter: raw source record (as stored by ingest) -> canonical row input.

Ingest stores firmware records verbatim (``agrifusion.ingest.record_store``). This is
the one place that interprets their shape for canonical:

* schema v2 (``RawTelemetryReporter``: ``sensor_record`` / ``sim_record`` /
  ``system_record``) is projected onto the *packet view*
  (``packet.npk_data`` / ``packet.sht30_data`` / ``packet.system_data`` + ``sensors``)
  that the canonical extractors read; ``system_record``/``sim_record``/``sensor_record``
  are passed through unchanged for the context extractors;
* legacy v1 records already ARE in the packet view (it is the firmware's own
  ``NodePacketBuilder`` shape and the v1 wire format), so they pass through as a copy.

Why the packet view is kept (instead of extractors that read v2 directly): v1 data
still has to be read in that shape, so keeping one extractor set and projecting v2
onto it means one code path and identical canonical values. The view is an internal
input of ``processors/*``, never written to disk.

This code moved here from ``ingest/sources/base.py`` (``_normalize_v2_record_payload``,
``_build_legacy_*``) without behavior changes. Dropped with the move (canonical never
read them): the v1 rewrites ``sensor_id``/``sensor_type`` defaults, ``transport``,
``battery_v == -1 -> None``, ``ip == "0.0.0.0"`` removal, long debug-string removal
and ``quality`` removal.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any


@dataclass(frozen=True)
class AdapterConfig:
    timezone: tzinfo
    npk_sensor_id: str = "soil_7in1_01"
    npk_sensor_type: str = "soil_multi_sensor"
    sht30_sensor_id: str = "air_sht30_01"
    sht30_sensor_type: str = "air_temp_humidity"

    @classmethod
    def from_settings(cls, settings: Any) -> "AdapterConfig":
        return cls(
            timezone=settings.timezone,
            npk_sensor_id=settings.npk_sensor_id,
            npk_sensor_type=settings.npk_sensor_type,
            sht30_sensor_id=settings.sht30_sensor_id,
            sht30_sensor_type=settings.sht30_sensor_type,
        )


def is_v2_record(record_payload: Any) -> bool:
    return (
        isinstance(record_payload, dict)
        and isinstance(record_payload.get("sensor_record"), dict)
        and isinstance(record_payload.get("sim_record"), dict)
        and isinstance(record_payload.get("system_record"), dict)
    )


class FirmwareRecordAdapter:
    def __init__(self, config: AdapterConfig):
        self.config = config

    def adapt(self, record_payload: dict[str, Any]) -> dict[str, Any]:
        """Return the row input for ``CanonicalRowBuilder``; never mutates the input."""
        if is_v2_record(record_payload):
            return self._adapt_v2(record_payload)
        return copy.deepcopy(record_payload)

    def _adapt_v2(self, record_payload: dict[str, Any]) -> dict[str, Any]:
        normalized = copy.deepcopy(record_payload)
        system_record: dict[str, Any] = normalized.get("system_record", {})
        time_payload: dict[str, Any] = system_record.get("time", {})
        identity_payload: dict[str, Any] = system_record.get("identity", {})
        sync_payload: dict[str, Any] = system_record.get("sync", {})
        sensor_record: dict[str, Any] = normalized.get("sensor_record", {})
        sim_record: dict[str, Any] = normalized.get("sim_record", {})

        ts_sample = self._resolve_v2_ts_sample(time_payload)
        ts_server = self._resolve_v2_ts_server(time_payload, ts_sample)
        date_key = self._resolve_v2_date_key(identity_payload, ts_sample)
        sample_time_local = self._format_local_iso(ts_sample)
        upload_time_local = self._format_local_iso(ts_server)

        npk_sensor_id, npk_sensor_payload = self._select_sensor_payload(
            sensor_record=sensor_record,
            preferred_id=self.config.npk_sensor_id,
            fallback_id="soil_7in1_01",
        )
        sht30_sensor_id, sht30_sensor_payload = self._select_sensor_payload(
            sensor_record=sensor_record,
            preferred_id=self.config.sht30_sensor_id,
            fallback_id="air_sht30_01",
        )

        npk_packet = self.build_npk_packet(npk_sensor_id, npk_sensor_payload)
        sht30_packet = self.build_sht30_packet(sht30_sensor_id, sht30_sensor_payload)

        return (
            {
                "schema_version": 2,
                "ts_sample": ts_sample,
                "ts_device": ts_sample,
                "ts_server": ts_server,
                "sample_time_local": sample_time_local,
                "upload_time_local": upload_time_local,
                "packet": {
                    "npk_data": npk_packet,
                    "sht30_data": sht30_packet,
                    "system_data": {
                        "sample_epoch_sec": ts_sample,
                        "sample_time_valid": bool(time_payload.get("time_valid")),
                        "sample_date_key": date_key,
                        "transport": sim_record.get("transport"),
                        "send_state": self.derive_send_state(sync_payload),
                    },
                },
                "sensors": {
                    "npk": self.build_sensor_trace(
                        sensor_id=npk_packet.get("sensor_id"),
                        sensor_type=npk_packet.get("sensor_type"),
                        read_status=npk_sensor_payload.get("read_status"),
                    ),
                    "sht30": self.build_sensor_trace(
                        sensor_id=sht30_packet.get("sensor_id"),
                        sensor_type=sht30_packet.get("sensor_type"),
                        read_status=sht30_sensor_payload.get("read_status"),
                    ),
                },
                "system_record": normalized.get("system_record"),
                "sim_record": normalized.get("sim_record"),
                "sensor_record": normalized.get("sensor_record"),
            }
        )


    def _resolve_v2_ts_sample(self, time_payload: dict[str, Any]) -> int | None:
        ts_sample = self._as_int(time_payload.get("ts_sample"))
        if ts_sample is not None and ts_sample > 0:
            return ts_sample
        return None

    def _resolve_v2_ts_server(self, time_payload: dict[str, Any], ts_sample: int | None) -> int | None:
        ts_server = self._as_int(time_payload.get("ts_server"))
        if ts_server is not None and ts_server > 0:
            return ts_server
        return ts_sample

    def _resolve_v2_date_key(self, identity_payload: dict[str, Any], ts_sample: int | None) -> str | None:
        record_path = str(identity_payload.get("record_path") or "")
        parts = [part for part in record_path.split("/") if part]
        if len(parts) >= 4 and parts[-3] == "telemetry":
            return parts[-2]
        if ts_sample is not None and ts_sample > 0:
            return datetime.fromtimestamp(ts_sample, tz=self.config.timezone).date().isoformat()
        return None

    def _select_sensor_payload(
        self,
        *,
        sensor_record: dict[str, Any],
        preferred_id: str,
        fallback_id: str,
    ) -> tuple[str, dict[str, Any]]:
        candidate = sensor_record.get(preferred_id)
        if isinstance(candidate, dict):
            return preferred_id, candidate
        candidate = sensor_record.get(fallback_id)
        if isinstance(candidate, dict):
            return fallback_id, candidate
        for sensor_id, payload in sensor_record.items():
            if isinstance(payload, dict):
                return str(sensor_id), payload
        return preferred_id, {}

    def build_npk_packet(self, sensor_id: str, sensor_payload: dict[str, Any]) -> dict[str, Any]:
        values = sensor_payload.get("values", {}) if isinstance(sensor_payload.get("values"), dict) else {}
        status = sensor_payload.get("read_status", {}) if isinstance(sensor_payload.get("read_status"), dict) else {}
        return (
            {
                "sensor_id": sensor_id or self.config.npk_sensor_id,
                "sensor_type": sensor_payload.get("sensor_type") or self.config.npk_sensor_type,
                "read_ok": bool(status.get("read_ok")),
                "npk_values_valid": bool(status.get("sample_valid")),
                "frame_ok": status.get("frame_ok"),
                "crc_ok": status.get("crc_ok"),
                "error_code": status.get("error_code"),
                "error_code_raw": status.get("raw_error_code"),
                "retry_count": status.get("retry_count"),
                "timeout_ms": status.get("timeout_ms"),
                "read_duration_ms": status.get("read_elapsed_ms"),
                "consecutive_fail_count": status.get("consecutive_fail_count"),
                "recovered_after_fail": status.get("recovered_after_fail"),
                "ph_state": status.get("ph_state"),
                "temp_protocol_ok": _status_field_value(status, "field_validity", "temp", "temp_protocol_ok"),
                "temp_value_valid": _status_field_value(status, "field_value_validity", "temp", "temp_value_valid"),
                "temp_source": _status_field_value(status, "field_source", "temp", "temp_source"),
                "hum_protocol_ok": _status_field_value(status, "field_validity", "hum", "hum_protocol_ok"),
                "hum_value_valid": _status_field_value(status, "field_value_validity", "hum", "hum_value_valid"),
                "hum_source": _status_field_value(status, "field_source", "hum", "hum_source"),
                "hum_calibration_status": _status_field_value(
                    status, "moisture_calibration", "status", "hum_calibration_status"
                ),
                "hum_calibration_profile": _status_field_value(
                    status, "moisture_calibration", "profile", "hum_calibration_profile"
                ),
                "hum_value_semantics": _status_field_value(
                    status, "moisture_calibration", "value_semantics", "hum_value_semantics"
                ),
                "hum_raw_adc": _status_field_value(
                    status, "moisture_calibration", "latest_raw_adc", "hum_raw_adc"
                ),
                "hum_voltage_mv": _status_field_value(
                    status, "moisture_calibration", "latest_voltage_mv", "hum_voltage_mv"
                ),
                "hum_install_depth_cm_min": _status_field_value(
                    status, "moisture_calibration", "install_depth_cm_min", "hum_install_depth_cm_min"
                ),
                "hum_install_depth_cm_max": _status_field_value(
                    status, "moisture_calibration", "install_depth_cm_max", "hum_install_depth_cm_max"
                ),
                "ph_protocol_ok": _status_field_value(status, "field_validity", "ph", "ph_protocol_ok"),
                "ph_value_valid": _status_field_value(status, "field_value_validity", "ph", "ph_value_valid"),
                "ph_source": _status_field_value(status, "field_source", "ph", "ph_source"),
                "ec_protocol_ok": _status_field_value(status, "field_validity", "ec", "ec_protocol_ok"),
                "ec_value_valid": _status_field_value(status, "field_value_validity", "ec", "ec_value_valid"),
                "ec_source": _status_field_value(status, "field_source", "ec", "ec_source"),
                "ec_measurement_kind": status.get("ec_measurement_kind"),
                "N_value_valid": _status_field_value(status, "field_value_validity", "N", "N_value_valid"),
                "N_source": _status_field_value(status, "field_source", "N", "N_source"),
                "P_value_valid": _status_field_value(status, "field_value_validity", "P", "P_value_valid"),
                "P_source": _status_field_value(status, "field_source", "P", "P_source"),
                "K_value_valid": _status_field_value(status, "field_value_validity", "K", "K_value_valid"),
                "K_source": _status_field_value(status, "field_source", "K", "K_source"),
                "temp": values.get("soil_temp_c"),
                "hum": values.get("soil_moisture_pct"),
                "ph": values.get("soil_ph"),
                "ec": values.get("soil_ec_us_cm"),
                "N": values.get("soil_n_proxy"),
                "P": values.get("soil_p_proxy"),
                "K": values.get("soil_k_proxy"),
            }
        )

    def build_sht30_packet(self, sensor_id: str, sensor_payload: dict[str, Any]) -> dict[str, Any]:
        values = sensor_payload.get("values", {}) if isinstance(sensor_payload.get("values"), dict) else {}
        status = sensor_payload.get("read_status", {}) if isinstance(sensor_payload.get("read_status"), dict) else {}
        return (
            {
                "sensor_id": sensor_id or self.config.sht30_sensor_id,
                "sensor_type": sensor_payload.get("sensor_type") or self.config.sht30_sensor_type,
                "sht_read_ok": bool(status.get("read_ok")),
                "sht_sample_valid": bool(status.get("sample_valid")),
                "sht_error": status.get("error_code"),
                "sht_retry_count": status.get("retry_count"),
                "sht_read_elapsed_ms": status.get("read_elapsed_ms"),
                "sht_invalid_streak": status.get("invalid_streak"),
                "sht_value_valid": status.get("value_valid"),
                "sht_values_available": status.get("values_available"),
                "sht_values_recorded_with_error": status.get("values_recorded_with_error"),
                "sht_observed_temp_c": status.get("observed_temp_c"),
                "sht_observed_hum_pct": status.get("observed_hum_pct"),
                "sht_i2c_address_ack": status.get("i2c_address_ack"),
                "sht_i2c_error": status.get("i2c_error"),
                "sht_frame_ok": status.get("frame_ok"),
                "sht_temp_crc_ok": status.get("temp_crc_ok"),
                "sht_hum_crc_ok": status.get("hum_crc_ok"),
                "sht_raw_temp": status.get("raw_temp"),
                "sht_raw_hum": status.get("raw_hum"),
                "sht_temp_c": values.get("air_temp_c"),
                "sht_hum_pct": values.get("air_rh_pct"),
            }
        )

    def build_sensor_trace(
        self,
        *,
        sensor_id: Any,
        sensor_type: Any,
        read_status: Any,
    ) -> dict[str, Any]:
        read_status = read_status if isinstance(read_status, dict) else {}
        read_ok = read_status.get("read_ok")
        sample_valid = read_status.get("sample_valid")
        error_code = read_status.get("error_code")
        status = read_status.get("status")
        if status is None:
            if sample_valid is False or (error_code not in (None, "", "ok", 0)):
                status = "error"
            elif read_ok is True and sample_valid is True:
                status = "ok"
        return (
            {
                "sensor_id": sensor_id,
                "sensor_type": sensor_type,
                "read_ok": read_ok,
                "sample_valid": sample_valid,
                "status": status,
                "error_code": error_code,
            }
        )

    def derive_send_state(self, sync_payload: dict[str, Any]) -> str:
        if not isinstance(sync_payload, dict):
            return "unknown"
        if bool(sync_payload.get("replayed")):
            return "replayed"
        if bool(sync_payload.get("buffered")):
            return "buffered"
        if bool(sync_payload.get("telemetry_persisted")):
            return "persisted"
        return "sampled"

    def _format_local_iso(self, ts_value: int | None) -> str | None:
        if ts_value is None or ts_value <= 0:
            return None
        return datetime.fromtimestamp(ts_value, tz=self.config.timezone).isoformat()

    def _as_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


def _status_field_value(
    status: dict[str, Any],
    object_key: str,
    field_key: str,
    scalar_key: str,
) -> Any:
    scalar_value = status.get(scalar_key)
    if scalar_value is not None:
        return scalar_value
    nested = status.get(object_key)
    if isinstance(nested, dict):
        return nested.get(field_key)
    return None
