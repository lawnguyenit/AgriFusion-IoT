from __future__ import annotations

from typing import Any

from ..common import clamp, safe_float, severity_from_confidence, summarize_issues

# These weights are internal confidence penalties for downstream agents.
# They are not vendor-provided percentages. The structure comes from:
# 1. protocol/driver certainty flags in the packet (read_ok, crc_ok, frame_ok),
# 2. the vendor caution that NPK on many 7-in-1 RS485 probes is indicative/storage-like,
# 3. field reliability assumptions that should be calibrated with local data.
READ_FAIL_PENALTY = 0.35
FRAME_FAIL_PENALTY = 0.20
CRC_FAIL_PENALTY = 0.20
VALUES_INVALID_PENALTY = 0.25
ALARM_PENALTY = 0.15
ERROR_CODE_PENALTY = 0.20
RETRY_PENALTY = 0.08
LOW_BATTERY_PENALTY = 0.05

# Vendor moisture accuracy is quoted around brown soil at 30% and 60% moisture.
# Below 30% we downgrade NPK trust because the dielectric/ionic context becomes
# less stable and the NPK estimate can drift sharply in dry soil.
LOW_MOISTURE_WARNING_PCT = 30.0
VERY_LOW_MOISTURE_PCT = 20.0
LOW_MOISTURE_PENALTY = 0.25
VERY_LOW_MOISTURE_EXTRA_PENALTY = 0.10


def assess_npk_health(
    packet_payload: dict[str, Any],
    sensor_payload: dict[str, Any],
    health_payload: dict[str, Any],
    overall_health: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    confidence = float(health_payload.get("quality") or sensor_payload.get("quality") or 0.75)
    soil_humidity_pct = safe_float(packet_payload.get("hum"))

    if not packet_payload.get("read_ok", False):
        confidence -= READ_FAIL_PENALTY
        issues.append("NPK read was not successful")
    if not packet_payload.get("frame_ok", False):
        confidence -= FRAME_FAIL_PENALTY
        issues.append("Modbus frame integrity is degraded")
    if not packet_payload.get("crc_ok", False):
        confidence -= CRC_FAIL_PENALTY
        issues.append("CRC validation failed")
    if not packet_payload.get("npk_values_valid", False):
        confidence -= VALUES_INVALID_PENALTY
        issues.append("NPK values are marked invalid")
    if packet_payload.get("sensor_alarm", False):
        confidence -= ALARM_PENALTY
        issues.append("Sensor alarm flag is active")

    error_code = str(packet_payload.get("error_code") or health_payload.get("error_code") or "")
    if error_code and error_code.lower() not in {"ok", "0"}:
        confidence -= ERROR_CODE_PENALTY
        issues.append(f"Sensor reported error code {error_code}")

    retry_count = int(packet_payload.get("retry_count") or 0)
    if retry_count >= 3:
        confidence -= RETRY_PENALTY
        issues.append("Read required multiple retries")

    if soil_humidity_pct is not None and soil_humidity_pct < LOW_MOISTURE_WARNING_PCT:
        confidence -= LOW_MOISTURE_PENALTY
        issues.append(
            "Soil humidity is below 30%, so NPK values are less trustworthy in dry soil"
        )
        if soil_humidity_pct < VERY_LOW_MOISTURE_PCT:
            confidence -= VERY_LOW_MOISTURE_EXTRA_PENALTY
            issues.append("Soil humidity is below 20%, which sharply increases NPK drift risk")

    if float(overall_health.get("battery_v") or 0.0) < 11.2:
        confidence -= LOW_BATTERY_PENALTY
        issues.append("Battery voltage is low for stable telemetry")

    confidence = clamp(confidence)
    if confidence >= 0.85 and not issues:
        status = "ok"
    elif confidence >= 0.55:
        status = "degraded"
    else:
        status = "fault"

    return {
        "status": status,
        "confidence": round(confidence, 4),
        "severity": severity_from_confidence(confidence),
        "issues": issues,
        "summary": summarize_issues(issues, fallback="NPK sensor health is stable"),
        "evidence": {
            "read_ok": bool(packet_payload.get("read_ok", False)),
            "frame_ok": bool(packet_payload.get("frame_ok", False)),
            "crc_ok": bool(packet_payload.get("crc_ok", False)),
            "npk_values_valid": bool(packet_payload.get("npk_values_valid", False)),
            "retry_count": retry_count,
            "soil_humidity_pct": soil_humidity_pct,
            "dry_soil_risk": bool(
                soil_humidity_pct is not None and soil_humidity_pct < LOW_MOISTURE_WARNING_PCT
            ),
            "battery_v": overall_health.get("battery_v"),
            "quality": health_payload.get("quality") or sensor_payload.get("quality"),
        },
    }
