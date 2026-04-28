from __future__ import annotations

from typing import Any

from ...utils.common import clamp, severity_from_confidence, summarize_issues

# These are internal confidence penalties, not Sensirion datasheet values.
# The datasheet tells us the sensor's nominal capability; the penalties below
# express how much downstream trust should drop when the driver reports bad reads.
READ_FAIL_PENALTY = 0.35
INVALID_SAMPLE_PENALTY = 0.25
ERROR_CODE_PENALTY = 0.20
INVALID_STREAK_STEP = 0.04
INVALID_STREAK_CAP = 0.20
RETRY_PENALTY = 0.05
LOW_BATTERY_PENALTY = 0.05


def assess_sht30_health(
    packet_payload: dict[str, Any],
    sensor_payload: dict[str, Any],
    health_payload: dict[str, Any],
    overall_health: dict[str, Any],
) -> dict[str, Any]:
    """
    Kiểm tra sức khỏe của cảm biến SHT30 dựa trên các chỉ số đọc được và trạng thái hệ thống, trả về một đánh giá tổng thể bao gồm:
    - Trạng thái sức khỏe (ok, degraded, fault)
    - Điểm tin cậy (confidence) từ 0 đến 1
    - Mức độ nghiêm trọng (severity) dựa trên điểm tin cậy
    - Các vấn đề cụ thể được xác định (issues)
    - Tóm tắt các vấn đề (summary)
    - Bằng chứng chi tiết hỗ trợ đánh giá (evidence)    

    Args:
        packet_payload (dict[str, Any]): _description_
        sensor_payload (dict[str, Any]): _description_
        health_payload (dict[str, Any]): _description_
        overall_health (dict[str, Any]): _description_

    Returns:
        dict[str, Any]: _description_
    """    
    issues: list[str] = []
    confidence = float(health_payload.get("quality") or sensor_payload.get("quality") or 0.8)

    if not packet_payload.get("sht_read_ok", False):
        confidence -= READ_FAIL_PENALTY
        issues.append("SHT30 read failed")
    if not packet_payload.get("sht_sample_valid", False):
        confidence -= INVALID_SAMPLE_PENALTY
        issues.append("SHT30 sample is invalid")

    error_code = str(packet_payload.get("sht_error") or health_payload.get("error_code") or "")
    if error_code and error_code.lower() not in {"ok", "0"}:
        confidence -= ERROR_CODE_PENALTY
        issues.append(f"SHT30 reported error code {error_code}")

    invalid_streak = int(packet_payload.get("sht_invalid_streak") or 0)
    if invalid_streak > 0:
        confidence -= min(INVALID_STREAK_CAP, invalid_streak * INVALID_STREAK_STEP)
        issues.append("SHT30 has a non-zero invalid streak")

    retry_count = int(packet_payload.get("sht_retry_count") or 0)
    if retry_count >= 2:
        confidence -= RETRY_PENALTY
        issues.append("SHT30 needed retries to complete a sample")

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
        "summary": summarize_issues(issues, fallback="SHT30 sensor health is stable"),
        "evidence": {
            "sht_read_ok": bool(packet_payload.get("sht_read_ok", False)),
            "sht_sample_valid": bool(packet_payload.get("sht_sample_valid", False)),
            "sht_invalid_streak": invalid_streak,
            "sht_retry_count": retry_count,
            "battery_v": overall_health.get("battery_v"),
            "quality": health_payload.get("quality") or sensor_payload.get("quality"),
        },
    }
