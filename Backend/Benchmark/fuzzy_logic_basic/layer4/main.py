from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.fuzzy_logic_basic.shared.config_loader import load_config
from Backend.Benchmark.fuzzy_logic_basic.shared.fuzzy_math import clamp01, piecewise_score_series, right_shoulder_series
from Backend.Config.IO.io_csv import load_csv, write_csv
from Backend.Config.path_manager import get_benchmark_path


@dataclass(frozen=True)
class PredictionResult:
    membership_csv: Path
    pressure_csv: Path
    dynamics_csv: Path
    output_csv: Path
    row_count: int


def default_membership_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_membership.csv"


def default_pressure_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_pressure.csv"


def default_dynamics_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_temporal_dynamics.csv"


def default_output_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_output_prediction.csv"


def _risk_level(score: float, levels: dict[str, float]) -> str:
    if score <= float(levels["normal_max"]):
        return "normal"
    if score <= float(levels["watch_max"]):
        return "watch"
    if score <= float(levels["warning_max"]):
        return "warning"
    return "critical"


def _recommendation(row: pd.Series, config: dict[str, float]) -> str:
    if float(row["sensor_uncertainty"]) >= float(config["sensor_uncertainty_high_min"]):
        return "sensor_check"
    if (
        float(row["water_pressure"]) >= float(config["reason_threshold"])
        and float(row["water_accumulated_pressure"]) >= float(config["water_accumulated_high_min"])
    ):
        return "irrigate_check"
    if (
        float(row["heat_pressure"]) >= float(config["reason_threshold"])
        and float(row["dry_air_pressure"]) >= float(config["reason_threshold"])
    ):
        return "monitor_heat_dry_air"
    if (
        float(row["nutrient_context_pressure"]) >= float(config["nutrient_pressure_high_min"])
        and int(row["reason_post_fertilization"]) == 1
    ):
        return "monitor_post_fertilization"
    if float(row["risk_score"]) <= float(config["risk_levels"]["normal_max"]) and float(row["confidence"]) >= float(config["confidence_high_min"]):
        return "keep"
    return "monitor"


def _audit_reason_text(row: pd.Series) -> str:
    labels = {
        "reason_water_low": "soil moisture is approaching dry boundary",
        "reason_water_dropping": "soil humidity trend is dropping",
        "reason_heat_high": "air temperature is in the hot band",
        "reason_soil_heat_high": "soil temperature is in the hot band",
        "reason_air_dry": "air humidity is in the dry band",
        "reason_ec_shift": "EC is outside the safe context band",
        "reason_ec_npk_inconsistent": "EC and NPK are inconsistent",
        "reason_ph_context": "pH is outside the stable context band",
        "reason_sensor_uncertain": "sensor confidence is low due to stale or inconsistent data",
        "reason_post_irrigation": "recent pattern suggests post-irrigation recovery context",
        "reason_post_fertilization": "recent pattern suggests post-fertilization context"
    }
    active = [text for key, text in labels.items() if int(row[key]) == 1]
    return "; ".join(active)


def build_prediction_output(
    membership_csv: Path | None = None,
    pressure_csv: Path | None = None,
    dynamics_csv: Path | None = None,
    output_csv: Path | None = None,
) -> PredictionResult:
    membership_path = membership_csv or default_membership_csv()
    pressure_path = pressure_csv or default_pressure_csv()
    dynamics_path = dynamics_csv or default_dynamics_csv()
    target_path = output_csv or default_output_csv()

    membership = load_csv(membership_path)
    pressure = load_csv(pressure_path)
    dynamics = load_csv(dynamics_path)

    risk_config = load_config("flb_risk_levels.json")
    dynamics_config = load_config("flb_dynamics_config.json")

    merged = membership.merge(pressure, on="timestamp", how="inner").merge(dynamics, on="timestamp", how="inner")

    accumulated_levels = dynamics_config["accumulated_pressure_levels"]
    merged["accumulated_pressure_score"] = piecewise_score_series(
        merged["plant_accumulated_pressure"],
        (
            float(accumulated_levels["watch_start"]),
            float(accumulated_levels["warning_start"]),
            float(accumulated_levels["critical_start"]),
        ),
    )

    merged["velocity_score"] = right_shoulder_series(
        merged[["water_velocity_to_boundary_3h", "heat_velocity_to_boundary_3h", "dry_air_velocity_to_boundary_3h"]].max(axis=1),
        zero_at_or_below=float(risk_config["trajectory_velocity_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_velocity_one_at_or_above"]),
    )
    merged["acceleration_score"] = right_shoulder_series(
        merged[["water_acceleration_to_boundary", "heat_acceleration_to_boundary", "dry_air_acceleration_to_boundary"]].max(axis=1),
        zero_at_or_below=float(risk_config["trajectory_acceleration_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_acceleration_one_at_or_above"]),
    )
    merged["trajectory_score"] = merged[["velocity_score", "acceleration_score"]].max(axis=1)

    weight_config = risk_config["risk_score_weights"]
    temporal_component = (
        merged["accumulated_pressure_score"] * float(weight_config["accumulated_pressure_score"])
        + merged["trajectory_score"] * float(weight_config["trajectory_score"])
    ) * merged["temporal_warmup_ratio"].astype(float)

    merged["risk_score"] = (
        merged["instant_pressure_total"].astype(float) * float(weight_config["instant_pressure_total"])
        + temporal_component
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    merged["risk_level"] = merged["risk_score"].apply(lambda value: _risk_level(float(value), risk_config["risk_levels"]))

    threshold = float(risk_config["reason_threshold"])
    merged["reason_water_low"] = (merged["soil_humidity_low"].astype(float) >= threshold).astype(int)
    merged["reason_water_dropping"] = (merged["soil_humidity_dropping"].astype(float) >= threshold).astype(int)
    merged["reason_heat_high"] = (merged["air_temperature_high"].astype(float) >= threshold).astype(int)
    merged["reason_soil_heat_high"] = (merged["soil_temperature_high"].astype(float) >= threshold).astype(int)
    merged["reason_air_dry"] = (merged["air_humidity_low"].astype(float) >= threshold).astype(int)
    merged["reason_ec_shift"] = (merged["EC_risk"].astype(float) >= threshold).astype(int)
    merged["reason_ec_npk_inconsistent"] = (merged["ec_npk_consistency_flag"].astype(float) < 1.0).astype(int)
    merged["reason_ph_context"] = (merged["pH_context_risk"].astype(float) >= threshold).astype(int)
    merged["reason_sensor_uncertain"] = (merged["sensor_uncertainty"].astype(float) >= float(risk_config["sensor_uncertainty_high_min"])).astype(int)
    merged["reason_post_irrigation"] = (merged["recent_irrigation_signal"].astype(float) >= threshold).astype(int)
    merged["reason_post_fertilization"] = (merged["recent_fertilization_signal"].astype(float) >= threshold).astype(int)

    merged["recommendation"] = merged.apply(lambda row: _recommendation(row, risk_config), axis=1)
    merged["audit_reason_text"] = merged.apply(_audit_reason_text, axis=1)
    merged["confidence"] = merged["confidence"].astype(float).apply(clamp01)

    columns = [
        "timestamp",
        "risk_score",
        "risk_level",
        "recommendation",
        "confidence",
        "audit_reason_text",
        "reason_water_low",
        "reason_water_dropping",
        "reason_heat_high",
        "reason_soil_heat_high",
        "reason_air_dry",
        "reason_ec_shift",
        "reason_ec_npk_inconsistent",
        "reason_ph_context",
        "reason_sensor_uncertain",
        "reason_post_irrigation",
        "reason_post_fertilization",
    ]
    write_csv(merged[columns], target_path)
    return PredictionResult(
        membership_csv=membership_path,
        pressure_csv=pressure_path,
        dynamics_csv=dynamics_path,
        output_csv=target_path,
        row_count=len(merged),
    )
