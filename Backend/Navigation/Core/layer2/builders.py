from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .timeseries import (
    add_datetime_columns,
    delta_1step,
    rolling_condition_duration_hours,
    rolling_condition_ratio,
    rolling_time_max,
    rolling_time_mean,
    rolling_time_min,
    rolling_time_range,
    rolling_time_slope,
)


BASE_COLUMNS = [
    "timestamp",
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]


@dataclass(frozen=True)
class Layer2FeatureConfig:
    air_humidity_saturation_threshold: float = 95.0


@dataclass(frozen=True)
class Layer2FeatureBundle:
    dataframe: pd.DataFrame
    base_columns: list[str]
    feature_groups: dict[str, list[str]]


def build_layer2_feature_bundle(
    dataframe: pd.DataFrame,
    config: Layer2FeatureConfig | None = None,
) -> Layer2FeatureBundle:
    feature_config = config or Layer2FeatureConfig()
    frame = add_datetime_columns(dataframe)

    feature_groups: dict[str, list[str]] = {
        "delta": [],
        "window_short": [],
        "window_medium": [],
        "window_long": [],
        "saturation": [],
    }

    for column in ("air_temp", "soil_temp", "soil_humidity", "EC"):
        feature_name = f"{column}_delta_1step"
        frame[feature_name] = delta_1step(frame[column])
        feature_groups["delta"].append(feature_name)

    short_columns = _build_short_window_features(frame)
    medium_columns = _build_medium_window_features(frame)
    long_columns = _build_long_window_features(frame)
    saturation_columns = _build_saturation_features(frame, feature_config)

    feature_groups["window_short"].extend(short_columns)
    feature_groups["window_medium"].extend(medium_columns)
    feature_groups["window_long"].extend(long_columns)
    feature_groups["saturation"].extend(saturation_columns)

    return Layer2FeatureBundle(
        dataframe=frame,
        base_columns=list(BASE_COLUMNS),
        feature_groups=feature_groups,
    )


def _build_short_window_features(frame: pd.DataFrame) -> list[str]:
    timestamps = frame["timestamp_dt"]
    created: list[str] = []

    frame["air_temp_slope_3h"] = rolling_time_slope(frame["air_temp"], timestamps, window_hours=3, min_points=3)
    frame["air_temp_range_3h"] = rolling_time_range(frame["air_temp"], timestamps, window_hours=3, min_points=2)
    frame["air_temp_mean_3h"] = rolling_time_mean(frame["air_temp"], timestamps, window_hours=3, min_points=1)
    created.extend(["air_temp_slope_3h", "air_temp_range_3h", "air_temp_mean_3h"])

    frame["soil_temp_slope_3h"] = rolling_time_slope(frame["soil_temp"], timestamps, window_hours=3, min_points=3)
    created.append("soil_temp_slope_3h")

    frame["soil_humidity_slope_3h"] = rolling_time_slope(frame["soil_humidity"], timestamps, window_hours=3, min_points=3)
    frame["soil_humidity_range_3h"] = rolling_time_range(frame["soil_humidity"], timestamps, window_hours=3, min_points=2)
    created.extend(["soil_humidity_slope_3h", "soil_humidity_range_3h"])

    frame["EC_slope_3h"] = rolling_time_slope(frame["EC"], timestamps, window_hours=3, min_points=3)
    frame["EC_range_3h"] = rolling_time_range(frame["EC"], timestamps, window_hours=3, min_points=2)
    created.extend(["EC_slope_3h", "EC_range_3h"])

    return created


def _build_medium_window_features(frame: pd.DataFrame) -> list[str]:
    timestamps = frame["timestamp_dt"]
    created: list[str] = []

    frame["air_temp_slope_8h"] = rolling_time_slope(frame["air_temp"], timestamps, window_hours=8, min_points=3)
    frame["air_temp_range_8h"] = rolling_time_range(frame["air_temp"], timestamps, window_hours=8, min_points=2)
    created.extend(["air_temp_slope_8h", "air_temp_range_8h"])

    frame["soil_temp_slope_8h"] = rolling_time_slope(frame["soil_temp"], timestamps, window_hours=8, min_points=3)
    frame["soil_temp_mean_8h"] = rolling_time_mean(frame["soil_temp"], timestamps, window_hours=8, min_points=1)
    created.extend(["soil_temp_slope_8h", "soil_temp_mean_8h"])

    frame["soil_humidity_slope_8h"] = rolling_time_slope(frame["soil_humidity"], timestamps, window_hours=8, min_points=3)
    frame["soil_humidity_range_8h"] = rolling_time_range(frame["soil_humidity"], timestamps, window_hours=8, min_points=2)
    created.extend(["soil_humidity_slope_8h", "soil_humidity_range_8h"])

    frame["EC_slope_8h"] = rolling_time_slope(frame["EC"], timestamps, window_hours=8, min_points=3)
    frame["EC_range_8h"] = rolling_time_range(frame["EC"], timestamps, window_hours=8, min_points=2)
    created.extend(["EC_slope_8h", "EC_range_8h"])

    return created


def _build_long_window_features(frame: pd.DataFrame) -> list[str]:
    timestamps = frame["timestamp_dt"]
    created: list[str] = []

    frame["soil_temp_range_24h"] = rolling_time_range(frame["soil_temp"], timestamps, window_hours=24, min_points=2)
    created.append("soil_temp_range_24h")

    frame["soil_humidity_mean_24h"] = rolling_time_mean(frame["soil_humidity"], timestamps, window_hours=24, min_points=1)
    frame["soil_humidity_min_24h"] = rolling_time_min(frame["soil_humidity"], timestamps, window_hours=24, min_points=1)
    created.extend(["soil_humidity_mean_24h", "soil_humidity_min_24h"])

    frame["EC_mean_24h"] = rolling_time_mean(frame["EC"], timestamps, window_hours=24, min_points=1)
    frame["EC_range_24h"] = rolling_time_range(frame["EC"], timestamps, window_hours=24, min_points=2)
    ec_high_local_mean = frame["EC"] >= frame["EC_mean_24h"]
    frame["EC_exposure_24h"] = rolling_condition_ratio(ec_high_local_mean, timestamps, window_hours=24)
    created.extend(["EC_mean_24h", "EC_range_24h", "EC_exposure_24h"])

    return created


def _build_saturation_features(
    frame: pd.DataFrame,
    config: Layer2FeatureConfig,
) -> list[str]:
    timestamps = frame["timestamp_dt"]
    created: list[str] = []

    saturation_flag = frame["air_humidity"].ge(config.air_humidity_saturation_threshold)
    frame["air_humidity_saturation_flag"] = saturation_flag.astype(int)
    frame["air_humidity_saturation_duration_3h"] = rolling_condition_duration_hours(
        saturation_flag,
        timestamps,
        frame["gap_hours_since_prev"],
        window_hours=3,
    )
    frame["air_humidity_saturation_duration_8h"] = rolling_condition_duration_hours(
        saturation_flag,
        timestamps,
        frame["gap_hours_since_prev"],
        window_hours=8,
    )
    frame["air_humidity_saturation_ratio_3h"] = (frame["air_humidity_saturation_duration_3h"] / 3.0).clip(lower=0.0, upper=1.0)
    frame["air_humidity_saturation_ratio_8h"] = (frame["air_humidity_saturation_duration_8h"] / 8.0).clip(lower=0.0, upper=1.0)
    created.extend(
        [
            "air_humidity_saturation_flag",
            "air_humidity_saturation_duration_3h",
            "air_humidity_saturation_duration_8h",
            "air_humidity_saturation_ratio_3h",
            "air_humidity_saturation_ratio_8h",
        ]
    )
    return created
