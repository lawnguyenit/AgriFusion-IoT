from __future__ import annotations

from typing import Any

from ...utils.common import clamp, severity_from_confidence, summarize_issues

MISSING_CORE_METRIC_PENALTY = 0.18
MISSING_SECONDARY_METRIC_PENALTY = 0.08


def assess_meteo_health(packet_payload: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    confidence = 0.92

    core_metrics = {
        "temperature_2m": packet_payload.get("temperature_2m"),
        "relative_humidity_2m": packet_payload.get("relative_humidity_2m"),
        "precipitation": packet_payload.get("precipitation"),
    }
    for metric_name, metric_value in core_metrics.items():
        if metric_value is None:
            confidence -= MISSING_CORE_METRIC_PENALTY
            issues.append(f"Missing core weather metric: {metric_name}")

    secondary_metrics = {
        "cloud_cover": packet_payload.get("cloud_cover"),
        "et0_fao_evapotranspiration": packet_payload.get("et0_fao_evapotranspiration"),
        "soil_temperature_0_to_7cm": packet_payload.get("soil_temperature_0_to_7cm"),
        "weather_code": packet_payload.get("weather_code"),
    }
    for metric_name, metric_value in secondary_metrics.items():
        if metric_value is None:
            confidence -= MISSING_SECONDARY_METRIC_PENALTY
            issues.append(f"Missing secondary weather metric: {metric_name}")

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
        "summary": summarize_issues(issues, fallback="Open-Meteo weather snapshot is usable"),
        "evidence": {
            "core_metrics_present": {
                metric_name: metric_value is not None
                for metric_name, metric_value in core_metrics.items()
            },
            "secondary_metrics_present": {
                metric_name: metric_value is not None
                for metric_name, metric_value in secondary_metrics.items()
            },
        },
    }
