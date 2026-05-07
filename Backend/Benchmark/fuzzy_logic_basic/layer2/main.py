from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.shared.config_loader import load_config
from Backend.Benchmark.fuzzy_logic_basic.shared.fuzzy_math import band_context_risk_series, clip01_series, left_shoulder_series, right_shoulder_series
from Backend.Benchmark.fuzzy_logic_basic.shared.timeseries import lag_at_or_before_hours, load_alignment_csv, rolling_time_slope
from Backend.Config.IO.io_csv import write_csv
from Backend.Config.path_manager import get_benchmark_path


@dataclass(frozen=True)
class MembershipResult:
    input_csv: Path
    output_csv: Path
    row_count: int


def default_input_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_input_aligned.csv"


def default_output_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_membership.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Layer 2 fuzzy membership CSV from FLB Layer 1 input.")
    parser.add_argument("--input-csv", type=Path, default=None, help="Path to flb_input_aligned.csv.")
    parser.add_argument("--output-csv", type=Path, default=None, help="Path to flb_membership.csv.")
    return parser.parse_args()


def build_membership(input_csv: Path | None = None, output_csv: Path | None = None) -> MembershipResult:

    # chuẩn bị dữ liệu và cấu hình
    membership_config = load_config("flb_membership_thresholds.json")
    dynamics_config = load_config("flb_dynamics_config.json")
    source_csv = input_csv or default_input_csv()
    target_csv = output_csv or default_output_csv()

    # tính toán các đặc trưng và membership values
    aligned = load_alignment_csv(source_csv)

    # copy để tránh SettingWithCopyWarning
    output = aligned.copy().sort_values("timestamp_dt").reset_index(drop=True)
    output["ec_npk_consistency_flag"] = (
        pd.to_numeric(output["ec_npk_consistency_score"], errors="coerce").fillna(0.0)
        >= 0.9
    ).astype(int)
    
    # tính gap_hours_since_prev để biết khoảng cách thời gian giữa các bản ghi, dùng để đánh giá độ tin cậy của slope và membership values dựa trên slope
    output["gap_hours_since_prev"] = output["timestamp_dt"].diff().dt.total_seconds().div(3600.0).fillna(0.0)

    # tính slope theo cửa sổ 3h cho các biến cần xu hướng tăng/giảm
    humidity_window = int(membership_config["soil_humidity_dropping"]["window_hours"])
    temperature_window = int(membership_config["soil_temperature_rising"]["window_hours"])
    air_temperature_window = int(membership_config["air_temperature_rising"]["window_hours"])
    air_humidity_window = int(membership_config["air_humidity_dropping"]["window_hours"])
    ec_window = int(membership_config["EC_rising"]["window_hours"])

    output["soil_humidity_slope_3h"] = rolling_time_slope(
        output["soil_humidity"],
        output["timestamp_dt"],
        humidity_window,
        min_points=3,
    )
    output["soil_temp_slope_3h"] = rolling_time_slope(
        output["soil_temp"],
        output["timestamp_dt"],
        temperature_window,
        min_points=3,
    )
    output["air_temp_slope_3h"] = rolling_time_slope(
        output["air_temp"],
        output["timestamp_dt"],
        air_temperature_window,
        min_points=3,
    )
    output["air_humidity_slope_3h"] = rolling_time_slope(
        output["air_humidity"],
        output["timestamp_dt"],
        air_humidity_window,
        min_points=3,
    )
    output["EC_slope_3h"] = rolling_time_slope(
        output["EC"],
        output["timestamp_dt"],
        ec_window,
        min_points=3,
    )
    ec_lag_24h = lag_at_or_before_hours(output["EC"], output["timestamp_dt"], 24.0)
    output["ec_delta_24h_strict"] = pd.to_numeric(output["EC"], errors="coerce").reset_index(drop=True) - ec_lag_24h

    output["soil_humidity_low"] = left_shoulder_series(
        output["soil_humidity"],
        one_at_or_below=float(membership_config["soil_humidity_low"]["one_at_or_below"]),
        zero_at_or_above=float(membership_config["soil_humidity_low"]["zero_at_or_above"]),
    )
    output["soil_humidity_high"] = right_shoulder_series(
        output["soil_humidity"],
        zero_at_or_below=float(membership_config["soil_humidity_high"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["soil_humidity_high"]["one_at_or_above"]),
    )
    output["soil_humidity_dropping"] = left_shoulder_series(
        output["soil_humidity_slope_3h"],
        one_at_or_below=float(membership_config["soil_humidity_dropping"]["one_at_or_below"]),
        zero_at_or_above=float(membership_config["soil_humidity_dropping"]["zero_at_or_above"]),
    )
    output["soil_humidity_rising"] = right_shoulder_series(
        output["soil_humidity_slope_3h"],
        zero_at_or_below=float(membership_config["soil_humidity_rising"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["soil_humidity_rising"]["one_at_or_above"]),
    )
    output["soil_temperature_low"] = left_shoulder_series(
        output["soil_temp"],
        one_at_or_below=float(membership_config["soil_temperature_low"]["one_at_or_below"]),
        zero_at_or_above=float(membership_config["soil_temperature_low"]["zero_at_or_above"]),
    )
    output["soil_temperature_high"] = right_shoulder_series(
        output["soil_temp"],
        zero_at_or_below=float(membership_config["soil_temperature_high"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["soil_temperature_high"]["one_at_or_above"]),
    )
    output["soil_temperature_rising"] = right_shoulder_series(
        output["soil_temp_slope_3h"],
        zero_at_or_below=float(membership_config["soil_temperature_rising"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["soil_temperature_rising"]["one_at_or_above"]),
    )
    output["air_temperature_low"] = left_shoulder_series(
        output["air_temp"],
        one_at_or_below=float(membership_config["air_temperature_low"]["one_at_or_below"]),
        zero_at_or_above=float(membership_config["air_temperature_low"]["zero_at_or_above"]),
    )
    output["air_temperature_high"] = right_shoulder_series(
        output["air_temp"],
        zero_at_or_below=float(membership_config["air_temperature_high"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["air_temperature_high"]["one_at_or_above"]),
    )
    output["air_temperature_rising"] = right_shoulder_series(
        output["air_temp_slope_3h"],
        zero_at_or_below=float(membership_config["air_temperature_rising"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["air_temperature_rising"]["one_at_or_above"]),
    )
    output["air_humidity_low"] = left_shoulder_series(
        output["air_humidity"],
        one_at_or_below=float(membership_config["air_humidity_low"]["one_at_or_below"]),
        zero_at_or_above=float(membership_config["air_humidity_low"]["zero_at_or_above"]),
    )
    output["air_humidity_high"] = right_shoulder_series(
        output["air_humidity"],
        zero_at_or_below=float(membership_config["air_humidity_high"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["air_humidity_high"]["one_at_or_above"]),
    )
    output["air_humidity_dropping"] = left_shoulder_series(
        output["air_humidity_slope_3h"],
        one_at_or_below=float(membership_config["air_humidity_dropping"]["one_at_or_below"]),
        zero_at_or_above=float(membership_config["air_humidity_dropping"]["zero_at_or_above"]),
    )
    output["EC_low_context"] = left_shoulder_series(
        output["EC"],
        one_at_or_below=float(membership_config["EC_low_context"]["one_at_or_below"]),
        zero_at_or_above=float(membership_config["EC_low_context"]["zero_at_or_above"]),
    )
    output["EC_high"] = right_shoulder_series(
        output["EC"],
        zero_at_or_below=float(membership_config["EC_high"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["EC_high"]["one_at_or_above"]),
    )
    output["EC_rising"] = right_shoulder_series(
        output["EC_slope_3h"],
        zero_at_or_below=float(membership_config["EC_rising"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["EC_rising"]["one_at_or_above"]),
    )
    output["EC_shift_24h"] = right_shoulder_series(
        output["ec_delta_24h_strict"].abs(),
        zero_at_or_below=float(membership_config["EC_shift_24h"]["zero_at_or_below"]),
        one_at_or_above=float(membership_config["EC_shift_24h"]["one_at_or_above"]),
    )
    ec_risk_parts = pd.concat(
        [
            output["EC_low_context"],
            output["EC_high"],
            output["EC_rising"],
            output["EC_shift_24h"],
        ],
        axis=1,
    )
    output["EC_risk"] = clip01_series(ec_risk_parts.max(axis=1))
    output["pH_context_risk"] = band_context_risk_series(
        output["pH"],
        safe_low=float(membership_config["pH_context_risk"]["safe_low"]),
        safe_high=float(membership_config["pH_context_risk"]["safe_high"]),
        warning_low=float(membership_config["pH_context_risk"]["warning_low"]),
        warning_high=float(membership_config["pH_context_risk"]["warning_high"]),
        critical_low=float(membership_config["pH_context_risk"]["critical_low"]),
        critical_high=float(membership_config["pH_context_risk"]["critical_high"]),
    )

    warmup_hours = float(dynamics_config["warmup_hours"])
    warmup_cutoff = output["timestamp_dt"].iloc[0] + pd.Timedelta(hours=warmup_hours)
    output = output.loc[output["timestamp_dt"] >= warmup_cutoff].copy().reset_index(drop=True)
    output["gap_hours_since_prev"] = output["timestamp_dt"].diff().dt.total_seconds().div(3600.0).fillna(0.0)
    output["warmup_ready_24h"] = 1

    columns = [
        "timestamp",
        "soil_temp",
        "soil_humidity",
        "air_temp",
        "air_humidity",
        "EC",
        "pH",
        "ec_npk_consistency_score",
        "ec_npk_consistency_flag",
        "warmup_ready_24h",
        "gap_hours_since_prev",
        "soil_humidity_slope_3h",
        "soil_temp_slope_3h",
        "air_temp_slope_3h",
        "air_humidity_slope_3h",
        "EC_slope_3h",
        "ec_delta_24h_strict",
        "soil_humidity_low",
        "soil_humidity_high",
        "soil_humidity_dropping",
        "soil_humidity_rising",
        "soil_temperature_low",
        "soil_temperature_high",
        "soil_temperature_rising",
        "air_temperature_low",
        "air_temperature_high",
        "air_temperature_rising",
        "air_humidity_low",
        "air_humidity_high",
        "air_humidity_dropping",
        "EC_low_context",
        "EC_high",
        "EC_rising",
        "EC_shift_24h",
        "EC_risk",
        "pH_context_risk",
    ]
    write_csv(output[columns], target_csv)
    return MembershipResult(input_csv=source_csv, output_csv=target_csv, row_count=len(output))


def main() -> None:
    args = parse_args()
    result = build_membership(input_csv=args.input_csv, output_csv=args.output_csv)
    print("Layer 2 fuzzy membership complete")
    print(f"Input CSV: {result.input_csv}")
    print(f"Output CSV: {result.output_csv}")
    print(f"Rows: {result.row_count}")


if __name__ == "__main__":
    main()
