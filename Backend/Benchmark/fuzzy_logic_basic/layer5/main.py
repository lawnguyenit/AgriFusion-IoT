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
class PathwayResult:
    input_csv: Path
    output_csv: Path
    row_count: int


def default_input_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_output_prediction.csv"


def default_output_csv() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_pathway_interpretation.csv"


def _score_row(row: pd.Series, weights: dict[str, float]) -> float:
    score = 0.0
    for key, weight in weights.items():
        value = row.get(key, 0)
        if pd.isna(value):
            value = 0.0
        score += float(weight) * float(value)
    return clamp01(score)


def _score_column_to_pathway(score_column: str) -> str:
    return score_column.removesuffix("_score")


def _pathway_reason_text(row: pd.Series, top_pathway: str) -> str:
    if top_pathway == "stable_no_dominant_pathway":
        return "no dominant pathway"
    if top_pathway == "water_stress_pathway":
        parts = []
        if int(row["reason_water_low"]) == 1:
            parts.append("soil moisture is approaching dry boundary")
        if int(row["reason_water_dropping"]) == 1:
            parts.append("soil humidity trend is dropping")
        if int(row["reason_post_irrigation"]) == 1:
            parts.append("recent irrigation context is still active")
        return "; ".join(parts)
    if top_pathway == "heat_stress_pathway":
        parts = []
        if int(row["reason_heat_high"]) == 1:
            parts.append("air temperature is in the hot band")
        if int(row["reason_soil_heat_high"]) == 1:
            parts.append("soil temperature is in the hot band")
        return "; ".join(parts)
    if top_pathway == "dry_air_pathway":
        return "air humidity is low and amplifying thermal stress"
    if top_pathway == "electrochemical_nutrient_context_pathway":
        parts = []
        if int(row["reason_ec_shift"]) == 1:
            parts.append("EC is outside the safe context band")
        if int(row["reason_ec_npk_inconsistent"]) == 1:
            parts.append("EC and NPK are inconsistent")
        if int(row["reason_ph_context"]) == 1:
            parts.append("pH is outside the stable context band")
        return "; ".join(parts)
    if top_pathway == "sensor_fault_pathway":
        return "sensor confidence is low due to stale or inconsistent data"
    if top_pathway == "post_intervention_pathway":
        parts = []
        if int(row["reason_post_irrigation"]) == 1:
            parts.append("post-irrigation recovery context")
        if int(row["reason_post_fertilization"]) == 1:
            parts.append("post-fertilization context")
        return "; ".join(parts)
    return "no dominant pathway"


def build_pathway_interpretation(
    output_csv: Path | None = None,
    pressure_csv: Path | None = None,
    dynamics_csv: Path | None = None,
    final_csv: Path | None = None,
) -> PathwayResult:
    source_csv = output_csv or default_input_csv()
    pressure_path = pressure_csv or (get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_pressure.csv")
    dynamics_path = dynamics_csv or (get_benchmark_path() / "fuzzy_logic_basic" / "dataset" / "flb_temporal_dynamics.csv")
    target_path = final_csv or default_output_csv()

    prediction = load_csv(source_csv)
    pressure = load_csv(pressure_path)
    dynamics = load_csv(dynamics_path)
    config = load_config("flb_pathways.json")
    risk_config = load_config("flb_risk_levels.json")
    dynamics_config = load_config("flb_dynamics_config.json")

    merged = (
        prediction.merge(
            pressure[
                [
                    "timestamp",
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
            ],
            on="timestamp",
            how="inner",
        )
        .merge(
            dynamics[
                [
                    "timestamp",
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
            ],
            on="timestamp",
            how="inner",
        )
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    accumulated_levels = dynamics_config["accumulated_pressure_levels"]
    merged["water_accumulated_pressure_score"] = piecewise_score_series(
        merged["water_accumulated_pressure"],
        (
            float(accumulated_levels["watch_start"]),
            float(accumulated_levels["warning_start"]),
            float(accumulated_levels["critical_start"]),
        ),
    )
    merged["heat_accumulated_pressure_score"] = piecewise_score_series(
        merged["heat_accumulated_pressure"],
        (
            float(accumulated_levels["watch_start"]),
            float(accumulated_levels["warning_start"]),
            float(accumulated_levels["critical_start"]),
        ),
    )
    merged["dry_air_accumulated_pressure_score"] = piecewise_score_series(
        merged["dry_air_accumulated_pressure"],
        (
            float(accumulated_levels["watch_start"]),
            float(accumulated_levels["warning_start"]),
            float(accumulated_levels["critical_start"]),
        ),
    )
    merged["nutrient_accumulated_pressure_score"] = piecewise_score_series(
        merged["nutrient_accumulated_pressure"],
        (
            float(accumulated_levels["watch_start"]),
            float(accumulated_levels["warning_start"]),
            float(accumulated_levels["critical_start"]),
        ),
    )

    merged["water_velocity_score"] = right_shoulder_series(
        merged["water_velocity_to_boundary_3h"],
        zero_at_or_below=float(risk_config["trajectory_velocity_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_velocity_one_at_or_above"]),
    )
    merged["heat_velocity_score"] = right_shoulder_series(
        merged["heat_velocity_to_boundary_3h"],
        zero_at_or_below=float(risk_config["trajectory_velocity_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_velocity_one_at_or_above"]),
    )
    merged["dry_air_velocity_score"] = right_shoulder_series(
        merged["dry_air_velocity_to_boundary_3h"],
        zero_at_or_below=float(risk_config["trajectory_velocity_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_velocity_one_at_or_above"]),
    )

    merged["water_acceleration_score"] = right_shoulder_series(
        merged["water_acceleration_to_boundary"],
        zero_at_or_below=float(risk_config["trajectory_acceleration_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_acceleration_one_at_or_above"]),
    )
    merged["heat_acceleration_score"] = right_shoulder_series(
        merged["heat_acceleration_to_boundary"],
        zero_at_or_below=float(risk_config["trajectory_acceleration_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_acceleration_one_at_or_above"]),
    )
    merged["dry_air_acceleration_score"] = right_shoulder_series(
        merged["dry_air_acceleration_to_boundary"],
        zero_at_or_below=float(risk_config["trajectory_acceleration_zero_at_or_below"]),
        one_at_or_above=float(risk_config["trajectory_acceleration_one_at_or_above"]),
    )

    pathway_weights = config["pathway_score_weights"]
    merged["water_stress_pathway_score"] = merged.apply(
        lambda row: _score_row(row, pathway_weights["water_stress_pathway"]), axis=1
    )
    merged["heat_stress_pathway_score"] = merged.apply(
        lambda row: _score_row(row, pathway_weights["heat_stress_pathway"]), axis=1
    )
    merged["dry_air_pathway_score"] = merged.apply(
        lambda row: _score_row(row, pathway_weights["dry_air_pathway"]), axis=1
    )
    merged["electrochemical_nutrient_context_pathway_score"] = merged.apply(
        lambda row: _score_row(row, pathway_weights["electrochemical_nutrient_context_pathway"]), axis=1
    )
    merged["sensor_fault_pathway_score"] = merged.apply(
        lambda row: _score_row(row, pathway_weights["sensor_fault_pathway"]), axis=1
    )
    merged["post_intervention_pathway_score"] = merged.apply(
        lambda row: _score_row(row, pathway_weights["post_intervention_pathway"]), axis=1
    )

    score_columns = [
        "water_stress_pathway_score",
        "heat_stress_pathway_score",
        "dry_air_pathway_score",
        "electrochemical_nutrient_context_pathway_score",
        "sensor_fault_pathway_score",
        "post_intervention_pathway_score",
    ]
    merged[score_columns] = merged[score_columns].fillna(0.0)
    merged["dominant_pathway"] = merged[score_columns].idxmax(axis=1).map(_score_column_to_pathway)
    merged["dominant_pathway_score"] = merged[score_columns].max(axis=1)
    merged["secondary_pathway"] = merged[score_columns].apply(
        lambda row: _score_column_to_pathway(str(row.sort_values(ascending=False).index[1])), axis=1
    )
    merged["secondary_pathway_score"] = merged[score_columns].apply(lambda row: float(row.sort_values(ascending=False).iloc[1]), axis=1)
    merged["pathway_margin"] = merged["dominant_pathway_score"] - merged["secondary_pathway_score"]
    merged["pathway_confidence"] = (
        merged["dominant_pathway_score"] * 0.7 + merged["pathway_margin"].clip(lower=0.0, upper=1.0) * 0.3
    ).clip(lower=0.0, upper=1.0)

    stable_threshold = float(config["stable_threshold"])
    dominance_threshold = float(config["dominance_threshold"])
    margin_threshold = float(config["margin_threshold"])

    merged["dominant_pathway"] = merged.apply(
        lambda row: "stable_no_dominant_pathway"
        if float(row["dominant_pathway_score"]) < stable_threshold or float(row["pathway_margin"]) < margin_threshold
        else str(row["dominant_pathway"]),
        axis=1,
    )
    merged["pathway_direction"] = merged.apply(
        lambda row: "toward_risk" if float(row["dominant_pathway_score"]) >= dominance_threshold else "stable",
        axis=1,
    )
    merged["pathway_reason_text"] = merged.apply(
        lambda row: _pathway_reason_text(row, str(row["dominant_pathway"])), axis=1
    )

    columns = [
        "timestamp",
        "dominant_pathway",
        "dominant_pathway_score",
        "secondary_pathway",
        "secondary_pathway_score",
        "pathway_margin",
        "pathway_confidence",
        "pathway_direction",
        "pathway_reason_text",
        "water_stress_pathway_score",
        "heat_stress_pathway_score",
        "dry_air_pathway_score",
        "electrochemical_nutrient_context_pathway_score",
        "sensor_fault_pathway_score",
        "post_intervention_pathway_score",
    ]
    write_csv(merged[columns], target_path)
    return PathwayResult(input_csv=source_csv, output_csv=target_path, row_count=len(merged))
