from __future__ import annotations

import pandas as pd

from Backend.Core.layer2.timeseries import (
    add_datetime_columns,
    delta_1step,
    rolling_time_mean,
    rolling_time_range,
    rolling_time_slope,
)
from Backend.Benchmark.context_benchmark.src.data.contracts import (
    RAW_CORE_SENSOR_COLUMNS,
    RAW_FULL_SENSOR_COLUMNS,
    V2_DELTA_COLUMNS,
    V2_WINDOW_SHORT_COLUMNS,
    V3_WINDOW_MEDIUM_COLUMNS,
)


METADATA_COLUMNS = ["context_label", "data_origin", "is_synthetic", "source_reference", "split_name"]


def build_v0_tabular(canonical_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["timestamp"] + RAW_FULL_SENSOR_COLUMNS + METADATA_COLUMNS
    return canonical_df[columns].copy()


def build_v1_tabular(canonical_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["timestamp"] + RAW_CORE_SENSOR_COLUMNS + METADATA_COLUMNS
    return canonical_df[columns].copy()


def build_v2_tabular(canonical_df: pd.DataFrame) -> pd.DataFrame:
    return _build_window_contract(
        canonical_df=canonical_df,
        include_medium_window=False,
    )


def build_v3_tabular(canonical_df: pd.DataFrame) -> pd.DataFrame:
    return _build_window_contract(
        canonical_df=canonical_df,
        include_medium_window=True,
    )


def _build_window_contract(
    *,
    canonical_df: pd.DataFrame,
    include_medium_window: bool,
) -> pd.DataFrame:
    base_columns = ["timestamp"] + RAW_CORE_SENSOR_COLUMNS + METADATA_COLUMNS
    ordered = canonical_df[base_columns].copy().sort_values("timestamp", kind="stable").reset_index(drop=True)
    group_columns = ["data_origin", "source_reference"] if "source_reference" in ordered.columns else ["data_origin"]
    groups: list[pd.DataFrame] = []

    for _, group in ordered.groupby(group_columns, dropna=False, sort=False):
        enriched = add_datetime_columns(group).copy()
        timestamps = enriched["timestamp_dt"]

        enriched["air_temp_delta_1step"] = delta_1step(enriched["air_temp"])
        enriched["soil_temp_delta_1step"] = delta_1step(enriched["soil_temp"])
        enriched["soil_humidity_delta_1step"] = delta_1step(enriched["soil_humidity"])
        enriched["EC_delta_1step"] = delta_1step(enriched["EC"])

        enriched["air_temp_slope_3h"] = rolling_time_slope(enriched["air_temp"], timestamps, window_hours=3, min_points=3)
        enriched["air_temp_range_3h"] = rolling_time_range(enriched["air_temp"], timestamps, window_hours=3, min_points=2)
        enriched["air_temp_mean_3h"] = rolling_time_mean(enriched["air_temp"], timestamps, window_hours=3, min_points=1)
        enriched["soil_temp_slope_3h"] = rolling_time_slope(enriched["soil_temp"], timestamps, window_hours=3, min_points=3)
        enriched["soil_humidity_slope_3h"] = rolling_time_slope(
            enriched["soil_humidity"], timestamps, window_hours=3, min_points=3
        )
        enriched["soil_humidity_range_3h"] = rolling_time_range(
            enriched["soil_humidity"], timestamps, window_hours=3, min_points=2
        )
        enriched["EC_slope_3h"] = rolling_time_slope(enriched["EC"], timestamps, window_hours=3, min_points=3)
        enriched["EC_range_3h"] = rolling_time_range(enriched["EC"], timestamps, window_hours=3, min_points=2)

        if include_medium_window:
            enriched["air_temp_slope_8h"] = rolling_time_slope(
                enriched["air_temp"], timestamps, window_hours=8, min_points=3
            )
            enriched["air_temp_range_8h"] = rolling_time_range(
                enriched["air_temp"], timestamps, window_hours=8, min_points=2
            )
            enriched["soil_temp_slope_8h"] = rolling_time_slope(
                enriched["soil_temp"], timestamps, window_hours=8, min_points=3
            )
            enriched["soil_temp_mean_8h"] = rolling_time_mean(
                enriched["soil_temp"], timestamps, window_hours=8, min_points=1
            )
            enriched["soil_humidity_slope_8h"] = rolling_time_slope(
                enriched["soil_humidity"], timestamps, window_hours=8, min_points=3
            )
            enriched["soil_humidity_range_8h"] = rolling_time_range(
                enriched["soil_humidity"], timestamps, window_hours=8, min_points=2
            )
            enriched["EC_slope_8h"] = rolling_time_slope(enriched["EC"], timestamps, window_hours=8, min_points=3)
            enriched["EC_range_8h"] = rolling_time_range(enriched["EC"], timestamps, window_hours=8, min_points=2)

        groups.append(enriched)

    combined = pd.concat(groups, ignore_index=True).sort_values("timestamp", kind="stable").reset_index(drop=True)
    selected_columns = (
        ["timestamp"]
        + RAW_CORE_SENSOR_COLUMNS
        + V2_DELTA_COLUMNS
        + V2_WINDOW_SHORT_COLUMNS
        + (V3_WINDOW_MEDIUM_COLUMNS if include_medium_window else [])
        + METADATA_COLUMNS
    )
    return combined[selected_columns].copy()
