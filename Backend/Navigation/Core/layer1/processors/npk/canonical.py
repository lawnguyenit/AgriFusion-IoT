from __future__ import annotations

from typing import Any

from ....utils.common import safe_float, safe_int
from ..common import as_optional_bool


def extract_npk_fields(packet_npk: dict[str, Any]) -> dict[str, Any]:
    packet_present = bool(packet_npk)
    temp_source = _field_source(packet_npk, "temp", "temp_source")
    moisture_source = _field_source(packet_npk, "hum", "hum_source")
    ec_source = _field_source(packet_npk, "ec", "ec_source")
    moisture_calibration = _nested_object(packet_npk, "moisture_calibration")
    moisture_value = safe_float(packet_npk.get("hum"))
    temp_value = safe_float(packet_npk.get("temp"))
    moisture_valid = _field_value_valid(packet_npk, "hum", "hum_value_valid")
    if moisture_valid is None:
        moisture_valid = moisture_value is not None and moisture_source != "unsupported_default_zero"
    temp_valid = _field_value_valid(packet_npk, "temp", "temp_value_valid")
    if temp_valid is None:
        temp_valid = temp_value is not None and temp_source != "unsupported_default_zero"
    ph_valid = _field_value_valid(packet_npk, "ph", "ph_value_valid")
    ec_valid = _field_value_valid(packet_npk, "ec", "ec_value_valid")
    n_valid = _field_value_valid(packet_npk, "N", "N_value_valid")
    p_valid = _field_value_valid(packet_npk, "P", "P_value_valid")
    k_valid = _field_value_valid(packet_npk, "K", "K_value_valid")
    return {
        "npk.soil_temp_c": temp_value,
        "npk.soil_moisture_pct": moisture_value,
        "npk.ph": safe_float(packet_npk.get("ph")),
        "npk.ec": safe_float(packet_npk.get("ec")),
        "npk.n_proxy": safe_float(packet_npk.get("N")),
        "npk.p_proxy": safe_float(packet_npk.get("P")),
        "npk.k_proxy": safe_float(packet_npk.get("K")),
        "npk.soil_temp_valid": temp_valid,
        "npk.soil_temp_source": temp_source,
        "npk.soil_moisture_valid": moisture_valid,
        "npk.soil_moisture_source": moisture_source,
        "npk.soil_moisture_calibration_status": _first_value(
            packet_npk.get("hum_calibration_status"), moisture_calibration.get("status")
        ),
        "npk.soil_moisture_calibration_profile": _first_value(
            packet_npk.get("hum_calibration_profile"), moisture_calibration.get("profile")
        ),
        "npk.soil_moisture_value_semantics": _first_value(
            packet_npk.get("hum_value_semantics"), moisture_calibration.get("value_semantics")
        ),
        "npk.soil_moisture_raw_adc": safe_int(
            _first_value(packet_npk.get("hum_raw_adc"), moisture_calibration.get("latest_raw_adc"))
        ),
        "npk.soil_moisture_voltage_mv": safe_int(
            _first_value(packet_npk.get("hum_voltage_mv"), moisture_calibration.get("latest_voltage_mv"))
        ),
        "npk.soil_moisture_install_depth_cm_min": safe_float(
            _first_value(packet_npk.get("hum_install_depth_cm_min"), moisture_calibration.get("install_depth_cm_min"))
        ),
        "npk.soil_moisture_install_depth_cm_max": safe_float(
            _first_value(packet_npk.get("hum_install_depth_cm_max"), moisture_calibration.get("install_depth_cm_max"))
        ),
        "npk.ph_protocol_ok": _field_protocol_valid(packet_npk, "ph", "ph_protocol_ok"),
        "npk.ph_valid": ph_valid,
        "npk.ph_status": packet_npk.get("ph_state"),
        "npk.ec_protocol_ok": _field_protocol_valid(packet_npk, "ec", "ec_protocol_ok"),
        "npk.ec_valid": ec_valid,
        "npk.ec_source": ec_source,
        "npk.ec_measurement_kind": _ec_measurement_kind(packet_npk, ec_source),
        "npk.n_proxy_valid": n_valid,
        "npk.p_proxy_valid": p_valid,
        "npk.k_proxy_valid": k_valid,
        "npk.packet_present": packet_present,
        "npk.error_code_raw": safe_int(packet_npk.get("error_code_raw")),
        "npk.crc_ok": as_optional_bool(packet_npk.get("crc_ok")),
        "npk.frame_ok": as_optional_bool(packet_npk.get("frame_ok")),
        "npk.signal_present": as_optional_bool(packet_npk.get("npk_signal_present")),
        "npk.values_valid": as_optional_bool(packet_npk.get("npk_values_valid")),
        "npk.retry_count": safe_int(packet_npk.get("retry_count")),
        "npk.consecutive_fail_count": safe_int(
            packet_npk.get("consecutive_fail_count")
        ),
        "npk.read_duration_ms": safe_int(packet_npk.get("read_duration_ms")),
    }


def _nested_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _field_source(payload: dict[str, Any], field: str, scalar_key: str) -> str | None:
    scalar = _first_value(payload.get(scalar_key))
    if scalar is not None:
        return str(scalar)
    source_map = _nested_object(payload, "field_source")
    value = source_map.get(field)
    return str(value) if value is not None and value != "" else None


def _field_value_valid(payload: dict[str, Any], field: str, scalar_key: str) -> bool | None:
    scalar = as_optional_bool(payload.get(scalar_key))
    if scalar is not None:
        return scalar
    value_map = _nested_object(payload, "field_value_validity")
    return as_optional_bool(value_map.get(field))


def _field_protocol_valid(payload: dict[str, Any], field: str, scalar_key: str) -> bool | None:
    scalar = as_optional_bool(payload.get(scalar_key))
    if scalar is not None:
        return scalar
    validity_map = _nested_object(payload, "field_validity")
    return as_optional_bool(validity_map.get(field))


def _ec_measurement_kind(payload: dict[str, Any], source: str | None) -> str | None:
    explicit = _first_value(payload.get("ec_measurement_kind"))
    if explicit is not None:
        return str(explicit)
    if source == "npk_proxy_derived":
        return "derived_proxy"
    if source == "modbus_register":
        return "observed_register"
    return "legacy_unknown" if payload.get("ec") is not None else None
