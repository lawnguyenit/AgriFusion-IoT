from __future__ import annotations

from typing import Any

from ..membership.functions import (
    EC_risk,
    air_humidity_low,
    air_temperature_high,
    clamp01,
    pH_risk,
    sensor_unreliable,
    soil_humidity_low,
    soil_temperature_high,
)


def build_pressure_scores(features: dict[str, Any], qc_features: dict[str, Any]) -> dict[str, float]:
    soil_humidity = features.get("soil_humidity_pct")
    soil_temp = features.get("soil_temp_c")
    air_temp = features.get("air_temperature_c")
    air_humidity = features.get("air_humidity_pct")
    ec_value = features.get("soil_ec_us_cm")
    ph_value = features.get("soil_ph")

    soil_humidity_low_score = soil_humidity_low(soil_humidity)
    soil_temperature_high_score = soil_temperature_high(soil_temp)
    air_temperature_high_score = air_temperature_high(air_temp)
    air_humidity_low_score = air_humidity_low(air_humidity)
    ec_risk_score = EC_risk(ec_value)
    ph_risk_score = pH_risk(ph_value)
    sensor_uncertainty_score = sensor_unreliable(qc_features)

    water_pressure = clamp01(
        max(
            soil_humidity_low_score,
            0.35 * soil_temperature_high_score + 0.35 * air_temperature_high_score + 0.30 * air_humidity_low_score,
        )
    )
    heat_pressure = clamp01(max(air_temperature_high_score, 0.6 * soil_temperature_high_score))
    dry_air_pressure = clamp01(max(air_humidity_low_score, 0.35 * air_temperature_high_score))
    nutrient_context_pressure = clamp01(max(ec_risk_score, 0.45 * ph_risk_score, 0.35 * sensor_uncertainty_score))
    sensor_uncertainty = clamp01(sensor_uncertainty_score)

    return {
        "soil_humidity_low": soil_humidity_low_score,
        "soil_temperature_high": soil_temperature_high_score,
        "air_temperature_high": air_temperature_high_score,
        "air_humidity_low": air_humidity_low_score,
        "EC_risk": ec_risk_score,
        "pH_risk": ph_risk_score,
        "sensor_unreliable": sensor_uncertainty_score,
        "water_pressure": water_pressure,
        "heat_pressure": heat_pressure,
        "dry_air_pressure": dry_air_pressure,
        "nutrient_context_pressure": nutrient_context_pressure,
        "sensor_uncertainty": sensor_uncertainty,
    }


def build_reason_codes(pressures: dict[str, float]) -> list[str]:
    codes: list[str] = []
    if pressures.get("soil_humidity_low", 0.0) >= 0.45:
        codes.append("soil moisture is approaching dry boundary")
    if pressures.get("heat_pressure", 0.0) >= 0.55 and pressures.get("water_pressure", 0.0) >= 0.35:
        codes.append("heat amplifies water stress")
    if pressures.get("dry_air_pressure", 0.0) >= 0.55:
        codes.append("dry air increases evaporative demand")
    if pressures.get("EC_risk", 0.0) >= 0.45:
        codes.append("EC is outside safe context")
    if pressures.get("pH_risk", 0.0) >= 0.55:
        codes.append("pH is drifting away from stable range")
    if pressures.get("sensor_uncertainty", 0.0) >= 0.55:
        codes.append("sensor confidence is low due to missing or stale data")
    return codes

