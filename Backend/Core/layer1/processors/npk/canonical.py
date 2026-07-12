from __future__ import annotations

from typing import Any

from ....utils.common import safe_float, safe_int
from ..common import as_optional_bool


def extract_npk_fields(packet_npk: dict[str, Any]) -> dict[str, Any]:
    packet_present = bool(packet_npk)
    return {
        "npk.soil_temp_c": safe_float(packet_npk.get("temp")),
        "npk.soil_moisture_pct": safe_float(packet_npk.get("hum")),
        "npk.ph": safe_float(packet_npk.get("ph")),
        "npk.ec": safe_float(packet_npk.get("ec")),
        "npk.n_proxy": safe_float(packet_npk.get("N")),
        "npk.p_proxy": safe_float(packet_npk.get("P")),
        "npk.k_proxy": safe_float(packet_npk.get("K")),
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
