from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from Backend.Benchmark.common.artifact_paths import resolve_dataset_artifact
from Backend.Benchmark.shared.labels import build_label_frame, merge_event_labels
from Backend.Benchmark.shared.split_policy import build_split_manifest, build_split_plan


class RawTabularBenchmarkConfig(Protocol):
    dataset_root: Path
    event_csv: Path
    train_ratio: float
    validation_ratio: float
    test_ratio: float
    split_strategy: str
    split_gap_minutes_override: int | None


@dataclass(frozen=True)
class RawTabularSourceSpec:
    source_kind: str
    source_csv_names: tuple[str, ...]
    feature_columns: tuple[str, ...]
    description: str


@dataclass
class RawTabularDataBundle:
    dataframe: pd.DataFrame
    feature_columns: list[str]
    source_kind: str
    source_csv: Path
    source_csvs: list[Path]
    split_counts: dict[str, int]
    split_slices: dict[str, slice]
    split_manifest: dict[str, object]
    row_count: int


def build_raw_tabular_source_registry() -> dict[str, RawTabularSourceSpec]:
    return {
        "v0": RawTabularSourceSpec(
            source_kind="v0",
            source_csv_names=("benchmark_input_aligned.csv",),
            feature_columns=(
                "soil_temp",
                "soil_humidity",
                "air_temp",
                "air_humidity",
                "EC",
                "pH",
                "N",
                "P",
                "K",
            ),
            description="Layer1 raw full sensor + chemistry baseline.",
        ),
        "v1": RawTabularSourceSpec(
            source_kind="v1",
            source_csv_names=("benchmark_input_aligned.csv",),
            feature_columns=(
                "soil_temp",
                "soil_humidity",
                "air_temp",
                "air_humidity",
                "EC",
            ),
            description="Layer1 environment + EC raw ablation arm.",
        ),
        "v2": RawTabularSourceSpec(
            source_kind="v2",
            source_csv_names=("single_window_exp2.csv",),
            feature_columns=(
                "soil_temp",
                "soil_humidity",
                "air_temp",
                "air_humidity",
                "EC",
                "air_temp_delta_1step",
                "soil_temp_delta_1step",
                "soil_humidity_delta_1step",
                "EC_delta_1step",
                "air_temp_slope_3h",
                "air_temp_range_3h",
                "air_temp_mean_3h",
                "soil_temp_slope_3h",
                "soil_humidity_slope_3h",
                "soil_humidity_range_3h",
                "EC_slope_3h",
                "EC_range_3h",
            ),
            description="Single-window raw tabular arm built from the 3h ablation export.",
        ),
        "v3": RawTabularSourceSpec(
            source_kind="v3",
            source_csv_names=("multi_window_combo2.csv",),
            feature_columns=(
                "soil_temp",
                "soil_humidity",
                "air_temp",
                "air_humidity",
                "EC",
                "air_temp_delta_1step",
                "soil_temp_delta_1step",
                "soil_humidity_delta_1step",
                "EC_delta_1step",
                "air_temp_slope_3h",
                "air_temp_range_3h",
                "air_temp_mean_3h",
                "soil_temp_slope_3h",
                "soil_humidity_slope_3h",
                "soil_humidity_range_3h",
                "EC_slope_3h",
                "EC_range_3h",
                "air_temp_slope_8h",
                "air_temp_range_8h",
                "soil_temp_slope_8h",
                "soil_temp_mean_8h",
                "soil_humidity_slope_8h",
                "soil_humidity_range_8h",
                "EC_slope_8h",
                "EC_range_8h",
            ),
            description="Combo raw tabular arm built from delta + 3h + 8h features.",
        ),
        "v4": RawTabularSourceSpec(
            source_kind="v4",
            source_csv_names=("single_window_exp6.csv",),
            feature_columns=(
                "soil_temp",
                "soil_humidity",
                "air_temp",
                "air_humidity",
                "EC",
                "air_temp_delta_1step",
                "soil_temp_delta_1step",
                "soil_humidity_delta_1step",
                "EC_delta_1step",
                "air_temp_slope_3h",
                "air_temp_range_3h",
                "air_temp_mean_3h",
                "soil_temp_slope_3h",
                "soil_humidity_slope_3h",
                "soil_humidity_range_3h",
                "EC_slope_3h",
                "EC_range_3h",
                "air_temp_slope_8h",
                "air_temp_range_8h",
                "soil_temp_slope_8h",
                "soil_temp_mean_8h",
                "soil_humidity_slope_8h",
                "soil_humidity_range_8h",
                "EC_slope_8h",
                "EC_range_8h",
                "soil_temp_range_24h",
                "soil_humidity_mean_24h",
                "soil_humidity_min_24h",
                "EC_mean_24h",
                "EC_range_24h",
                "EC_exposure_24h",
                "air_humidity_saturation_flag",
                "air_humidity_saturation_duration_3h",
                "air_humidity_saturation_duration_8h",
                "air_humidity_saturation_ratio_3h",
                "air_humidity_saturation_ratio_8h",
            ),
            description="Full single-window raw tabular arm.",
        ),
        "v5": RawTabularSourceSpec(
            source_kind="v5",
            source_csv_names=("benchmark_input_aligned.csv", "single_window_exp6.csv"),
            feature_columns=(
                "soil_temp",
                "soil_humidity",
                "air_temp",
                "air_humidity",
                "EC",
                "pH",
                "N",
                "P",
                "K",
                "air_temp_delta_1step",
                "soil_temp_delta_1step",
                "soil_humidity_delta_1step",
                "EC_delta_1step",
                "air_temp_slope_3h",
                "air_temp_range_3h",
                "air_temp_mean_3h",
                "soil_temp_slope_3h",
                "soil_humidity_slope_3h",
                "soil_humidity_range_3h",
                "EC_slope_3h",
                "EC_range_3h",
                "air_temp_slope_8h",
                "air_temp_range_8h",
                "soil_temp_slope_8h",
                "soil_temp_mean_8h",
                "soil_humidity_slope_8h",
                "soil_humidity_range_8h",
                "EC_slope_8h",
                "EC_range_8h",
                "soil_temp_range_24h",
                "soil_humidity_mean_24h",
                "soil_humidity_min_24h",
                "EC_mean_24h",
                "EC_range_24h",
                "EC_exposure_24h",
                "air_humidity_saturation_flag",
                "air_humidity_saturation_duration_3h",
                "air_humidity_saturation_duration_8h",
                "air_humidity_saturation_ratio_3h",
                "air_humidity_saturation_ratio_8h",
            ),
            description="Union raw tabular arm: Layer1 raw plus the full single-window engineered feature set.",
        ),
    }


def resolve_raw_tabular_source_paths(dataset_root: Path, registry_item: RawTabularSourceSpec) -> tuple[Path, ...]:
    return tuple(resolve_dataset_artifact(dataset_root, name) for name in registry_item.source_csv_names)


def _load_source_dataframe(source_csv: Path) -> pd.DataFrame:
    frame = pd.read_csv(source_csv)
    if "timestamp" not in frame.columns:
        raise ValueError(f"timestamp column not found in source CSV: {source_csv}")
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp", kind="stable").drop_duplicates(subset=["timestamp"], keep="last")
    return frame.reset_index(drop=True)


def _join_additional_source(base_frame: pd.DataFrame, source_frame: pd.DataFrame) -> pd.DataFrame:
    new_columns = [column for column in source_frame.columns if column != "timestamp" and column not in base_frame.columns]
    if not new_columns:
        return base_frame
    payload = source_frame[["timestamp"] + new_columns]
    merged = base_frame.merge(payload, on="timestamp", how="left", validate="one_to_one")
    return merged


def _assign_split_labels(frame: pd.DataFrame, split_plan) -> pd.DataFrame:
    labeled = frame.copy()
    labeled["split"] = "excluded_gap"
    for segment in split_plan.segments:
        labeled.iloc[segment.start : segment.stop, labeled.columns.get_loc("split")] = segment.name
    return labeled


def build_raw_tabular_data_bundle(config: RawTabularBenchmarkConfig, experiment_name: str) -> RawTabularDataBundle:
    registry = build_raw_tabular_source_registry()
    spec = registry.get(experiment_name)
    if spec is None:
        raise ValueError(f"Unsupported raw tabular experiment: {experiment_name}")

    source_paths = resolve_raw_tabular_source_paths(config.dataset_root, spec)
    if not source_paths:
        raise ValueError(f"No source CSVs configured for {experiment_name}")

    frame = _load_source_dataframe(source_paths[0])
    for source_path in source_paths[1:]:
        frame = _join_additional_source(frame, _load_source_dataframe(source_path))

    missing_columns = [column for column in spec.feature_columns if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Missing feature columns for {experiment_name}: {missing_columns}")

    merged_frame, _label_merge_report = merge_event_labels(frame, config.event_csv)
    labeled_frame = build_label_frame(merged_frame)
    split_plan = build_split_plan(
        row_count=len(labeled_frame),
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        strategy_name=config.split_strategy,
        timestamps=labeled_frame["timestamp"].tolist(),
        feature_columns=spec.feature_columns,
        gap_minutes_override=config.split_gap_minutes_override,
        coverage_labels=labeled_frame["four_class_label_name"].tolist(),
        normal_label="normal_context",
    )
    labeled_frame = _assign_split_labels(labeled_frame, split_plan)
    split_manifest = build_split_manifest(dataframe=labeled_frame, split_plan=split_plan)
    return RawTabularDataBundle(
        dataframe=labeled_frame,
        feature_columns=list(spec.feature_columns),
        source_kind=experiment_name,
        source_csv=source_paths[0],
        source_csvs=list(source_paths),
        split_counts=split_plan.split_counts,
        split_slices=split_plan.split_slices,
        split_manifest=split_manifest,
        row_count=len(labeled_frame),
    )
