from __future__ import annotations

from dataclasses import dataclass


BASE_COLUMNS = [
    "timestamp",
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
]

DELTA_COLUMNS = [
    "air_temp_delta_1step",
    "soil_temp_delta_1step",
    "soil_humidity_delta_1step",
    "EC_delta_1step",
]

WINDOW_SHORT_COLUMNS = [
    "air_temp_slope_3h",
    "air_temp_range_3h",
    "air_temp_mean_3h",
    "soil_temp_slope_3h",
    "soil_humidity_slope_3h",
    "soil_humidity_range_3h",
    "EC_slope_3h",
    "EC_range_3h",
]

WINDOW_MEDIUM_COLUMNS = [
    "air_temp_slope_8h",
    "air_temp_range_8h",
    "soil_temp_slope_8h",
    "soil_temp_mean_8h",
    "soil_humidity_slope_8h",
    "soil_humidity_range_8h",
    "EC_slope_8h",
    "EC_range_8h",
]

WINDOW_LONG_COLUMNS = [
    "soil_temp_range_24h",
    "soil_humidity_mean_24h",
    "soil_humidity_min_24h",
    "EC_mean_24h",
    "EC_range_24h",
    "EC_exposure_24h",
]

SATURATION_COLUMNS = [
    "air_humidity_saturation_flag",
    "air_humidity_saturation_duration_3h",
    "air_humidity_saturation_duration_8h",
    "air_humidity_saturation_ratio_3h",
    "air_humidity_saturation_ratio_8h",
]


@dataclass(frozen=True)
class Layer2ExperimentSpec:
    name: str
    description: str
    output_filename: str
    feature_columns: list[str]


def build_experiment_specs() -> dict[str, Layer2ExperimentSpec]:
    return {
        "exp1": Layer2ExperimentSpec(
            name="exp1",
            description="L1 base columns plus one-step delta features.",
            output_filename="flb_l2_exp1.csv",
            feature_columns=list(BASE_COLUMNS) + list(DELTA_COLUMNS),
        ),
        "exp2": Layer2ExperimentSpec(
            name="exp2",
            description="Exp1 plus 3h short-window features.",
            output_filename="flb_l2_exp2.csv",
            feature_columns=list(BASE_COLUMNS) + list(DELTA_COLUMNS) + list(WINDOW_SHORT_COLUMNS),
        ),
        "exp3": Layer2ExperimentSpec(
            name="exp3",
            description="Exp1 plus 8h medium-window features.",
            output_filename="flb_l2_exp3.csv",
            feature_columns=list(BASE_COLUMNS) + list(DELTA_COLUMNS) + list(WINDOW_MEDIUM_COLUMNS),
        ),
        "exp4": Layer2ExperimentSpec(
            name="exp4",
            description="Exp1 plus 24h long-window summaries and EC exposure.",
            output_filename="flb_l2_exp4.csv",
            feature_columns=list(BASE_COLUMNS) + list(DELTA_COLUMNS) + list(WINDOW_LONG_COLUMNS),
        ),
        "exp5": Layer2ExperimentSpec(
            name="exp5",
            description="Exp1 plus air-humidity saturation persistence features.",
            output_filename="flb_l2_exp5.csv",
            feature_columns=list(BASE_COLUMNS) + list(DELTA_COLUMNS) + list(SATURATION_COLUMNS),
        ),
        "exp6": Layer2ExperimentSpec(
            name="exp6",
            description="Full L2 ablation set: delta, 3h, 8h, 24h, and saturation.",
            output_filename="flb_l2_exp6.csv",
            feature_columns=(
                list(BASE_COLUMNS)
                + list(DELTA_COLUMNS)
                + list(WINDOW_SHORT_COLUMNS)
                + list(WINDOW_MEDIUM_COLUMNS)
                + list(WINDOW_LONG_COLUMNS)
                + list(SATURATION_COLUMNS)
            ),
        ),
    }
