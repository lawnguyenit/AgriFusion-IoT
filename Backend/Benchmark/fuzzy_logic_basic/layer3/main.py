from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.shared.config_loader import load_config
from Backend.Benchmark.fuzzy_logic_basic.shared.fuzzy_math import clip01_series, left_shoulder_series, right_shoulder_series, weighted_sum_series
from Backend.Benchmark.fuzzy_logic_basic.shared.timeseries import rolling_time_max, rolling_time_mean
from Backend.Config.IO.io_csv import load_csv, write_csv
from Backend.Config.path_manager import get_benchmark_path


@dataclass(frozen=True)
class PressureResult:
    input_csv: Path
    output_csv: Path
    row_count: int


def default_input_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_membership.csv"


def default_output_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_pressure.csv"


def build_pressure(input_csv: Path | None = None, output_csv: Path | None = None) -> PressureResult:
    source_csv = input_csv or default_input_csv()
    target_csv = output_csv or default_output_csv()
    membership = load_csv(source_csv).copy()
    membership["timestamp_dt"] = pd.to_datetime(membership["timestamp"], unit="s", utc=True)

    pressure_config = load_config("flb_pressure_weights.json")
    dynamics_config = load_config("flb_dynamics_config.json")

    dry_window = int(dynamics_config["dry_duration_window_hours"])
    irrigation_window = int(dynamics_config["no_recent_irrigation_window_hours"])
    fertilization_window = int(dynamics_config["post_fertilization_window_hours"])

    membership["recent_irrigation_signal"] = membership["soil_humidity_rising"].astype(float)
    membership["dry_duration_score"] = clip01_series(
        rolling_time_mean(
            membership["soil_humidity_low"],
            membership["timestamp_dt"],
            dry_window,
            min_points=max(2, dry_window // 2),
        )
    )
    membership["no_recent_irrigation_score"] = clip01_series(
        1.0
        - rolling_time_max(
            membership["recent_irrigation_signal"],
            membership["timestamp_dt"],
            irrigation_window,
            min_points=1,
        ).fillna(0.0)
    )
    membership["recent_fertilization_signal"] = clip01_series(
        rolling_time_max(
            membership["EC_rising"],
            membership["timestamp_dt"],
            fertilization_window,
            min_points=4,
        ).fillna(0.0)
    )
    membership["ec_npk_inconsistency"] = clip01_series(1.0 - membership["ec_npk_consistency_score"].astype(float))

    water_weights = pressure_config["water_pressure"]
    membership["water_pressure"] = weighted_sum_series(
        [
            (membership["soil_humidity_low"], float(water_weights["soil_humidity_low"])),
            (membership["soil_humidity_dropping"], float(water_weights["soil_humidity_dropping"])),
            (membership["dry_duration_score"], float(water_weights["dry_duration_score"])),
            (membership["no_recent_irrigation_score"], float(water_weights["no_recent_irrigation_score"])),
        ]
    )

    heat_weights = pressure_config["heat_pressure"]
    membership["heat_pressure"] = weighted_sum_series(
        [
            (membership["air_temperature_high"], float(heat_weights["air_temperature_high"])),
            (membership["soil_temperature_high"], float(heat_weights["soil_temperature_high"])),
            (membership["air_temperature_rising"], float(heat_weights["air_temperature_rising"])),
            (membership["soil_temperature_rising"], float(heat_weights["soil_temperature_rising"])),
        ]
    )

    dry_air_weights = pressure_config["dry_air_pressure"]
    dry_air_amplifier = clip01_series(
        membership["air_humidity_low"].astype(float) * membership["air_temperature_high"].astype(float)
    )
    membership["dry_air_pressure"] = weighted_sum_series(
        [
            (membership["air_humidity_low"], float(dry_air_weights["air_humidity_low"])),
            (membership["air_humidity_dropping"], float(dry_air_weights["air_humidity_dropping"])),
            (dry_air_amplifier, float(dry_air_weights["heat_amplifier"])),
        ]
    )

    nutrient_weights = pressure_config["nutrient_context_pressure"]
    membership["nutrient_context_pressure"] = weighted_sum_series(
        [
            (membership["EC_low_context"], float(nutrient_weights["EC_low_context"])),
            (membership["EC_high"], float(nutrient_weights["EC_high"])),
            (membership["EC_rising"], float(nutrient_weights["EC_rising"])),
            (membership["EC_shift_24h"], float(nutrient_weights["EC_shift_24h"])),
            (membership["ec_npk_inconsistency"], float(nutrient_weights["ec_npk_inconsistency"])),
            (membership["pH_context_risk"], float(nutrient_weights["pH_context_risk"])),
        ]
    )

    core_columns = ["soil_temp", "soil_humidity", "air_temp", "air_humidity", "EC", "pH"]
    membership["missing_core_ratio"] = membership[core_columns].isna().sum(axis=1) / float(len(core_columns))

    stale_config = dynamics_config["sensor_uncertainty"]
    membership["stale_data_score"] = right_shoulder_series(
        membership["gap_hours_since_prev"],
        zero_at_or_below=float(stale_config["stale_zero_at_or_below_hours"]),
        one_at_or_above=float(stale_config["stale_one_at_or_above_hours"]),
    )
    membership["electrochemical_uncertainty"] = right_shoulder_series(
        membership["ec_npk_inconsistency"],
        zero_at_or_below=float(stale_config["electrochemical_zero_at_or_below"]),
        one_at_or_above=float(stale_config["electrochemical_one_at_or_above"]),
    )

    uncertainty_weights = pressure_config["sensor_uncertainty"]
    membership["sensor_uncertainty"] = weighted_sum_series(
        [
            (membership["missing_core_ratio"], float(uncertainty_weights["missing_core_ratio"])),
            (membership["stale_data_score"], float(uncertainty_weights["stale_data_score"])),
            (membership["electrochemical_uncertainty"], float(uncertainty_weights["electrochemical_uncertainty"])),
        ]
    )

    instant_weights = pressure_config["instant_pressure_total"]
    membership["instant_pressure_total"] = weighted_sum_series(
        [
            (membership["water_pressure"], float(instant_weights["water_pressure"])),
            (membership["heat_pressure"], float(instant_weights["heat_pressure"])),
            (membership["dry_air_pressure"], float(instant_weights["dry_air_pressure"])),
            (membership["nutrient_context_pressure"], float(instant_weights["nutrient_context_pressure"])),
        ]
    )
    membership["plant_pressure"] = membership["instant_pressure_total"]
    membership["confidence"] = clip01_series(1.0 - membership["sensor_uncertainty"])

    columns = [
        "timestamp",
        "warmup_ready_24h",
        "water_pressure",
        "heat_pressure",
        "dry_air_pressure",
        "nutrient_context_pressure",
        "sensor_uncertainty",
        "instant_pressure_total",
        "plant_pressure",
        "confidence",
        "dry_duration_score",
        "no_recent_irrigation_score",
        "recent_irrigation_signal",
        "recent_fertilization_signal",
        "missing_core_ratio",
        "stale_data_score",
        "electrochemical_uncertainty",
        "ec_npk_inconsistency",
    ]
    write_csv(membership[columns], target_csv)
    return PressureResult(input_csv=source_csv, output_csv=target_csv, row_count=len(membership))
