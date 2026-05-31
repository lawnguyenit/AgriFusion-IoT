from __future__ import annotations

from dataclasses import dataclass
from math import exp
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.shared.config_loader import load_config
from Backend.Benchmark.fuzzy_logic_basic.shared.fuzzy_math import clip01_series
from Backend.Benchmark.fuzzy_logic_basic.shared.timeseries import rolling_time_slope
from Backend.Config.IO.io_csv import load_csv, write_csv
from Backend.Config.paths import BACKEND_PATHS


@dataclass(frozen=True)
class DynamicsResult:
    input_csv: Path
    output_csv: Path
    row_count: int


def default_input_csv() -> Path:
    return BACKEND_PATHS.benchmark_dir / "fuzzy_logic_basic" / "dataset" / "flb_pressure.csv"


def default_output_csv() -> Path:
    return BACKEND_PATHS.benchmark_dir / "fuzzy_logic_basic" / "dataset" / "flb_temporal_dynamics.csv"


def _accumulate_pressure(series: pd.Series, dt_hours: pd.Series, tau_hours: float) -> pd.Series:
    values: list[float] = []
    previous = 0.0
    for pressure_value, dt in zip(series.fillna(0.0), dt_hours.fillna(1.0), strict=False):
        decay = exp(-float(dt) / max(float(tau_hours), 1e-9))
        previous = decay * previous + float(pressure_value) * float(dt)
        values.append(previous)
    return pd.Series(values, index=series.index, dtype=float)


def build_temporal_dynamics(input_csv: Path | None = None, output_csv: Path | None = None) -> DynamicsResult:
    source_csv = input_csv or default_input_csv()
    target_csv = output_csv or default_output_csv()
    pressure = load_csv(source_csv).copy()
    config = load_config("flb_dynamics_config.json")

    pressure = pressure.sort_values("timestamp").reset_index(drop=True)
    pressure["timestamp_dt"] = pd.to_datetime(pressure["timestamp"], unit="s", utc=True)
    pressure["dt_hours"] = pressure["timestamp_dt"].diff().dt.total_seconds().div(3600.0).fillna(1.0).clip(lower=1e-6)

    tau_hours = config["tau_hours"]
    pressure["water_accumulated_pressure"] = _accumulate_pressure(pressure["water_pressure"], pressure["dt_hours"], float(tau_hours["water"]))
    pressure["heat_accumulated_pressure"] = _accumulate_pressure(pressure["heat_pressure"], pressure["dt_hours"], float(tau_hours["heat"]))
    pressure["dry_air_accumulated_pressure"] = _accumulate_pressure(pressure["dry_air_pressure"], pressure["dt_hours"], float(tau_hours["dry_air"]))
    pressure["nutrient_accumulated_pressure"] = _accumulate_pressure(
        pressure["nutrient_context_pressure"],
        pressure["dt_hours"],
        float(tau_hours["nutrient"]),
    )
    pressure["plant_accumulated_pressure"] = _accumulate_pressure(
        pressure["plant_pressure"],
        pressure["dt_hours"],
        float(tau_hours["plant"]),
    )

    velocity_windows = config["velocity_windows_hours"]
    short_window = max(2, int(velocity_windows["short"]))
    fast_window = max(1, int(velocity_windows["fast"]))
    long_window = max(short_window + 1, int(velocity_windows["long"]))

    for pressure_name, distance_name in [
        ("water_pressure", "water_distance_to_boundary"),
        ("heat_pressure", "heat_distance_to_boundary"),
        ("dry_air_pressure", "dry_air_distance_to_boundary"),
    ]:
        pressure[distance_name] = 1.0 - pressure[pressure_name].astype(float)

    pressure["water_velocity_to_boundary_3h"] = -rolling_time_slope(
        pressure["water_distance_to_boundary"], pressure["timestamp_dt"], short_window, min_points=3
    )
    pressure["heat_velocity_to_boundary_3h"] = -rolling_time_slope(
        pressure["heat_distance_to_boundary"], pressure["timestamp_dt"], short_window, min_points=3
    )
    pressure["dry_air_velocity_to_boundary_3h"] = -rolling_time_slope(
        pressure["dry_air_distance_to_boundary"], pressure["timestamp_dt"], short_window, min_points=3
    )

    water_velocity_fast = -rolling_time_slope(
        pressure["water_distance_to_boundary"], pressure["timestamp_dt"], fast_window, min_points=2
    )
    heat_velocity_fast = -rolling_time_slope(
        pressure["heat_distance_to_boundary"], pressure["timestamp_dt"], fast_window, min_points=2
    )
    dry_velocity_fast = -rolling_time_slope(
        pressure["dry_air_distance_to_boundary"], pressure["timestamp_dt"], fast_window, min_points=2
    )

    water_velocity_long = -rolling_time_slope(
        pressure["water_distance_to_boundary"], pressure["timestamp_dt"], long_window, min_points=4
    )
    heat_velocity_long = -rolling_time_slope(
        pressure["heat_distance_to_boundary"], pressure["timestamp_dt"], long_window, min_points=4
    )
    dry_velocity_long = -rolling_time_slope(
        pressure["dry_air_distance_to_boundary"], pressure["timestamp_dt"], long_window, min_points=4
    )

    pressure["water_acceleration_to_boundary"] = water_velocity_fast - water_velocity_long
    pressure["heat_acceleration_to_boundary"] = heat_velocity_fast - heat_velocity_long
    pressure["dry_air_acceleration_to_boundary"] = dry_velocity_fast - dry_velocity_long

    pressure["plant_distance_to_boundary"] = 1.0 - pressure["plant_pressure"].astype(float)
    pressure["plant_velocity_to_boundary_3h"] = -rolling_time_slope(
        pressure["plant_distance_to_boundary"], pressure["timestamp_dt"], short_window, min_points=3
    )

    warmup_hours = float(config["warmup_hours"])
    if "warmup_ready_24h" in pressure.columns:
        pressure["temporal_warmup_ratio"] = clip01_series(pd.to_numeric(pressure["warmup_ready_24h"], errors="coerce").fillna(0.0))
    else:
        elapsed_hours = pressure["dt_hours"].cumsum()
        pressure["temporal_warmup_ratio"] = clip01_series(elapsed_hours / max(warmup_hours, 1e-9))

    recovery_config = config["recovery"]
    pressure["recovery_signal"] = clip01_series(
        (-pressure["plant_velocity_to_boundary_3h"] / max(float(recovery_config["velocity_recovery_scale"]), 1e-9))
        * (1.0 - pressure["plant_pressure"].astype(float))
    )
    pressure["recovery_debt"] = clip01_series(
        pressure["plant_accumulated_pressure"] / max(float(recovery_config["debt_scale"]), 1e-9)
        - pressure["recovery_signal"]
    )

    columns = [
        "timestamp",
        "dt_hours",
        "water_accumulated_pressure",
        "heat_accumulated_pressure",
        "dry_air_accumulated_pressure",
        "nutrient_accumulated_pressure",
        "plant_accumulated_pressure",
        "water_velocity_to_boundary_3h",
        "heat_velocity_to_boundary_3h",
        "dry_air_velocity_to_boundary_3h",
        "water_acceleration_to_boundary",
        "heat_acceleration_to_boundary",
        "dry_air_acceleration_to_boundary",
        "temporal_warmup_ratio",
        "recovery_signal",
        "recovery_debt",
    ]
    write_csv(pressure[columns], target_csv)
    return DynamicsResult(input_csv=source_csv, output_csv=target_csv, row_count=len(pressure))
