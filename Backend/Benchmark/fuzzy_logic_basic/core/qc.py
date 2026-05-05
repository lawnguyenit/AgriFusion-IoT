from __future__ import annotations

from typing import Any

from .loader import extract_perception
from .model import MAX_METEO_STALE_SEC, MAX_NPK_STALE_SEC, MAX_SHT_STALE_SEC


def build_qc_features(
    current_rows: dict[str, Any],
    anchor_ts: int,
    ec_pred_slope: float,
    ec_pred_intercept: float,
) -> dict[str, Any]:
    sht_row = current_rows.get("sht30")
    npk_row = current_rows.get("npk")
    meteo_row = current_rows.get("meteo")

    core_rows = [row for row in (sht_row, npk_row, meteo_row) if row is not None]
    missing_core_count = 3 - len(core_rows)
    source_coverage_ratio = len(core_rows) / 3.0

    stale_values: list[float] = []
    for row, max_age_sec in ((sht_row, MAX_SHT_STALE_SEC), (npk_row, MAX_NPK_STALE_SEC), (meteo_row, MAX_METEO_STALE_SEC)):
        if row is None:
            stale_values.append(max_age_sec / 3600.0)
            continue
        stale_values.append(max(0.0, (anchor_ts - row.ts_server) / 3600.0))

    read_ok = len(core_rows) == 3
    values_valid = True
    flatline_ratio = 0.0
    ec_residual_ratio = 0.0

    if npk_row is not None:
        npk_perception = extract_perception(npk_row.payload)
        values_valid = all(
            npk_perception.get(key) is not None
            for key in ("n_ppm", "p_ppm", "k_ppm", "soil_temp_c", "soil_humidity_pct", "soil_ph", "soil_ec_us_cm")
        )
        n_val = float(npk_perception.get("n_ppm") or 0.0)
        p_val = float(npk_perception.get("p_ppm") or 0.0)
        k_val = float(npk_perception.get("k_ppm") or 0.0)
        ec_val = float(npk_perception.get("soil_ec_us_cm") or 0.0)
        ec_expected = ec_pred_intercept + ec_pred_slope * (n_val + p_val + k_val)
        if ec_expected > 0:
            ec_residual_ratio = abs(ec_val - ec_expected) / ec_expected
        read_ok = read_ok and values_valid

    return {
        "missing_core_count": missing_core_count,
        "missing_core_ratio": missing_core_count / 3.0,
        "source_coverage_ratio": source_coverage_ratio,
        "stale_sht30_hours": stale_values[0],
        "stale_npk_hours": stale_values[1],
        "stale_meteo_hours": stale_values[2],
        "max_stale_hours": max(stale_values) if stale_values else 0.0,
        "read_ok": read_ok,
        "values_valid": values_valid,
        "ec_residual_ratio": ec_residual_ratio,
        "flatline_ratio": flatline_ratio,
    }

