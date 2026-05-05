from __future__ import annotations

from typing import Any


def clamp01(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def linear_rise(value: float | int | None, start: float, end: float) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    if numeric <= start:
        return 0.0
    if numeric >= end:
        return 1.0
    if end == start:
        return 1.0
    return (numeric - start) / (end - start)


def linear_fall(value: float | int | None, start: float, end: float) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    if numeric <= start:
        return 1.0
    if numeric >= end:
        return 0.0
    if end == start:
        return 0.0
    return (end - numeric) / (end - start)


def soil_humidity_low(value: float | int | None) -> float:
    return clamp01(linear_fall(value, 30.0, 55.0))


def soil_temperature_high(value: float | int | None) -> float:
    return clamp01(linear_rise(value, 32.0, 39.0))


def air_temperature_high(value: float | int | None) -> float:
    return clamp01(linear_rise(value, 33.0, 40.0))


def air_humidity_low(value: float | int | None) -> float:
    return clamp01(linear_fall(value, 45.0, 75.0))


def EC_risk(value: float | int | None) -> float:
    return clamp01(linear_rise(value, 600.0, 1100.0))


def pH_risk(value: float | int | None) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    acid_side = 0.0
    if numeric <= 5.0:
        acid_side = 1.0
    elif numeric < 5.8:
        acid_side = (5.8 - numeric) / (5.8 - 5.0)

    alkaline_side = 0.0
    if numeric >= 7.5:
        alkaline_side = 1.0
    elif numeric > 6.8:
        alkaline_side = (numeric - 6.8) / (7.5 - 6.8)

    return clamp01(max(acid_side, alkaline_side))


def sensor_unreliable(qc_features: dict[str, Any]) -> float:
    missing_ratio = float(qc_features.get("missing_core_ratio") or 0.0)
    stale_hours = float(qc_features.get("max_stale_hours") or 0.0)
    ec_residual_ratio = float(qc_features.get("ec_residual_ratio") or 0.0)
    read_ok = bool(qc_features.get("read_ok", True))
    values_valid = bool(qc_features.get("values_valid", True))
    source_coverage = float(qc_features.get("source_coverage_ratio") or 1.0)
    flatline_ratio = float(qc_features.get("flatline_ratio") or 0.0)

    stale_score = linear_rise(stale_hours, 0.5, 2.0)
    residual_score = linear_rise(ec_residual_ratio, 0.12, 0.35)
    coverage_score = linear_fall(source_coverage, 0.35, 0.85)
    flatline_score = linear_rise(flatline_ratio, 0.4, 0.85)
    flag_score = 1.0 if (not read_ok or not values_valid) else 0.0

    score = max(
        missing_ratio,
        stale_score,
        residual_score,
        coverage_score,
        flatline_score,
        flag_score,
    )
    return clamp01(score)

