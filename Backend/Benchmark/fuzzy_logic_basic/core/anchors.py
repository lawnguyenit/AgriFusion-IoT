from __future__ import annotations

from typing import Any

try:
    from Backend.Config.data_utils import safe_float
except ImportError:
    from ....Config.data_utils import safe_float

from .loader import extract_perception
from .model import WINDOW_DAYS, StreamIndex

try:
    from Backend.Config.IO.io_json import write_json
except ImportError:
    from ...Config.IO.io_json import write_json


def fit_ec_model(npk_records: list[Any]) -> tuple[float, float]:
    pairs: list[tuple[float, float]] = []
    for record in npk_records:
        perception = extract_perception(record.payload)
        n_val = safe_float(perception.get("n_ppm"))
        p_val = safe_float(perception.get("p_ppm"))
        k_val = safe_float(perception.get("k_ppm"))
        ec_val = safe_float(perception.get("soil_ec_us_cm"))
        if None in (n_val, p_val, k_val, ec_val):
            continue
        pairs.append((n_val + p_val + k_val, ec_val))

    if not pairs:
        return 0.0, 0.0

    count = float(len(pairs))
    sum_x = sum(x for x, _ in pairs)
    sum_y = sum(y for _, y in pairs)
    sum_xx = sum(x * x for x, _ in pairs)
    sum_xy = sum(x * y for x, y in pairs)
    denom = count * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-9:
        return 0.0, sum_y / count
    slope = (count * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / count
    return slope, intercept


def build_era_features(meteo_series: StreamIndex, anchor_ts: int) -> dict[str, Any]:
    lower_bound = anchor_ts - WINDOW_DAYS * 24 * 3600
    window_records = [record for record in meteo_series.records if lower_bound <= record.ts_server <= anchor_ts]
    temp_values = [extract_perception(record.payload).get("temp_air_c") for record in window_records]
    humidity_values = [extract_perception(record.payload).get("humidity_air_pct") for record in window_records]
    rain_values = [extract_perception(record.payload).get("rain_mm") for record in window_records]
    precipitation_values = [extract_perception(record.payload).get("precipitation_mm") for record in window_records]
    dew_values = [extract_perception(record.payload).get("dew_point_c") for record in window_records]
    cloud_values = [extract_perception(record.payload).get("cloud_cover_pct") for record in window_records]
    soil_temp_values = [extract_perception(record.payload).get("soil_temp_0_7cm_c") for record in window_records]
    et0_values = [extract_perception(record.payload).get("et0_mm") for record in window_records]

    def avg(values: list[Any]) -> float | None:
        numeric = [float(value) for value in values if value is not None]
        if not numeric:
            return None
        return sum(numeric) / len(numeric)

    def total(values: list[Any]) -> float:
        return sum(float(value) for value in values if value is not None)

    return {
        "era_window_start_ts": lower_bound,
        "era_window_end_ts": anchor_ts,
        "era_sample_count": len(window_records),
        "era_temp_air_c_avg": avg(temp_values),
        "era_humidity_air_pct_avg": avg(humidity_values),
        "era_rain_mm_sum": total(rain_values),
        "era_precipitation_mm_sum": total(precipitation_values),
        "era_dew_point_c_avg": avg(dew_values),
        "era_cloud_cover_pct_avg": avg(cloud_values),
        "era_soil_temp_0_7cm_c_avg": avg(soil_temp_values),
        "era_et0_mm_sum": total(et0_values),
    }
