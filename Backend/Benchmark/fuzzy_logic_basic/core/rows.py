from __future__ import annotations

from typing import Any

try:
    from Backend.Config.data_utils import iso_from_ts, safe_float
except ImportError:
    from ....Config.data_utils import iso_from_ts, safe_float

from .dynamics import build_dynamics
from .loader import extract_perception
from .rules import build_pressure_scores, build_reason_codes


def build_row(
    anchor_ts: int,
    current_rows: dict[str, Any],
    era_features: dict[str, Any],
    qc_features: dict[str, Any],
    ec_pred_slope: float,
    ec_pred_intercept: float,
    previous_state: dict[str, dict[str, float]],
) -> dict[str, Any]:
    sht_row = current_rows.get("sht30")
    npk_row = current_rows.get("npk")
    meteo_row = current_rows.get("meteo")

    sht_perception = extract_perception(sht_row.payload) if sht_row else {}
    npk_perception = extract_perception(npk_row.payload) if npk_row else {}
    meteo_perception = extract_perception(meteo_row.payload) if meteo_row else {}

    air_temp = safe_float(meteo_perception.get("temp_air_c"))
    if air_temp is None:
        air_temp = safe_float(sht_perception.get("temp_air_c"))
    air_humidity = safe_float(sht_perception.get("humidity_air_pct"))
    if air_humidity is None:
        air_humidity = safe_float(meteo_perception.get("humidity_air_pct"))

    features = {
        "soil_humidity_pct": safe_float(npk_perception.get("soil_humidity_pct")),
        "soil_temperature_c": safe_float(npk_perception.get("soil_temp_c")),
        "air_temperature_c": air_temp,
        "air_humidity_pct": air_humidity,
        "soil_ec_us_cm": safe_float(npk_perception.get("soil_ec_us_cm")),
        "soil_ph": safe_float(npk_perception.get("soil_ph")),
    }

    pressures = build_pressure_scores(
        {
            "soil_humidity_pct": features["soil_humidity_pct"],
            "soil_temp_c": features["soil_temperature_c"],
            "air_temperature_c": features["air_temperature_c"],
            "air_humidity_pct": features["air_humidity_pct"],
            "soil_ec_us_cm": features["soil_ec_us_cm"],
            "soil_ph": features["soil_ph"],
        },
        qc_features,
    )

    dynamics = build_dynamics(pressures=pressures, previous_state=previous_state)
    reason_codes = build_reason_codes(pressures)

    ec_expected = None
    ec_residual_ratio = qc_features.get("ec_residual_ratio")
    n_val = safe_float(npk_perception.get("n_ppm")) or 0.0
    p_val = safe_float(npk_perception.get("p_ppm")) or 0.0
    k_val = safe_float(npk_perception.get("k_ppm")) or 0.0
    ec_value = safe_float(npk_perception.get("soil_ec_us_cm"))
    if ec_value is not None:
        ec_expected = ec_pred_intercept + ec_pred_slope * (n_val + p_val + k_val)

    row: dict[str, Any] = {
        "anchor_time_ts": anchor_ts,
        "anchor_time_local": iso_from_ts(anchor_ts),
        "anchor_source_family": max(
            ((name, record.ts_server) for name, record in current_rows.items() if record is not None),
            key=lambda item: item[1],
            default=("unknown", anchor_ts),
        )[0],
        "sht30_ts": None if sht_row is None else sht_row.ts_server,
        "npk_ts": None if npk_row is None else npk_row.ts_server,
        "meteo_ts": None if meteo_row is None else meteo_row.ts_server,
        "sht30_stale_hours": qc_features.get("stale_sht30_hours"),
        "npk_stale_hours": qc_features.get("stale_npk_hours"),
        "meteo_stale_hours": qc_features.get("stale_meteo_hours"),
        "max_stale_hours": qc_features.get("max_stale_hours"),
        "missing_core_ratio": qc_features.get("missing_core_ratio"),
        "source_coverage_ratio": qc_features.get("source_coverage_ratio"),
        "read_ok": qc_features.get("read_ok"),
        "values_valid": qc_features.get("values_valid"),
        "ec_pred_slope": ec_pred_slope,
        "ec_pred_intercept": ec_pred_intercept,
        "ec_expected_from_npk": ec_expected,
        "ec_residual_ratio": ec_residual_ratio,
        "ifs_temp_air_c": safe_float(meteo_perception.get("temp_air_c")),
        "ifs_humidity_air_pct": safe_float(meteo_perception.get("humidity_air_pct")),
        "ifs_rain_mm": safe_float(meteo_perception.get("rain_mm")),
        "ifs_precipitation_mm": safe_float(meteo_perception.get("precipitation_mm")),
        "ifs_dew_point_c": safe_float(meteo_perception.get("dew_point_c")),
        "ifs_cloud_cover_pct": safe_float(meteo_perception.get("cloud_cover_pct")),
        "ifs_soil_temp_0_7cm_c": safe_float(meteo_perception.get("soil_temp_0_7cm_c")),
        "ifs_et0_mm": safe_float(meteo_perception.get("et0_mm")),
        "sht_temp_air_c": safe_float(sht_perception.get("temp_air_c")),
        "sht_humidity_air_pct": safe_float(sht_perception.get("humidity_air_pct")),
        "soil_temperature_c": features["soil_temperature_c"],
        "soil_humidity_pct": features["soil_humidity_pct"],
        "soil_ph": features["soil_ph"],
        "soil_ec_us_cm": features["soil_ec_us_cm"],
        "n_ppm": n_val,
        "p_ppm": p_val,
        "k_ppm": k_val,
        "soil_humidity_low": pressures["soil_humidity_low"],
        "soil_temperature_high": pressures["soil_temperature_high"],
        "air_temperature_high": pressures["air_temperature_high"],
        "air_humidity_low": pressures["air_humidity_low"],
        "EC_risk": pressures["EC_risk"],
        "pH_risk": pressures["pH_risk"],
        "sensor_unreliable": pressures["sensor_unreliable"],
        "water_pressure": pressures["water_pressure"],
        "heat_pressure": pressures["heat_pressure"],
        "dry_air_pressure": pressures["dry_air_pressure"],
        "nutrient_context_pressure": pressures["nutrient_context_pressure"],
        "sensor_uncertainty": pressures["sensor_uncertainty"],
        "reason_codes": "|".join(reason_codes),
    }
    row.update(era_features)
    row.update(dynamics)
    return row
