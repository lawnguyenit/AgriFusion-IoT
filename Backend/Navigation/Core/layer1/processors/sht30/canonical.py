from __future__ import annotations

from typing import Any

from ....utils.common import safe_float, safe_int


def extract_sht30_fields(packet_sht: dict[str, Any]) -> dict[str, Any]:
    packet_present = bool(packet_sht)
    return {
        "sht.temp_c": safe_float(packet_sht.get("sht_temp_c")),
        "sht.humidity_pct": safe_float(packet_sht.get("sht_hum_pct")),
        "sht.packet_present": packet_present,
        "sht.retry_count": safe_int(packet_sht.get("sht_retry_count")),
        "sht.read_elapsed_ms": safe_int(packet_sht.get("sht_read_elapsed_ms")),
    }
