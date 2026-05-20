from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.pretrain_supervised.split_policy.artifacts import build_split_manifest
from Backend.Benchmark.pretrain_supervised.split_policy.builder import build_split_plan
from Backend.Benchmark.pretrain_supervised.v1.src.data.labels import build_label_frame, merge_event_labels
from Backend.Benchmark.direct_benchmark.src.config.settings import DirectBenchmarkConfig
from Backend.Benchmark.direct_benchmark.src.data.contracts import DirectDataBundle
from Backend.Benchmark.direct_benchmark.src.data.source_registry import build_direct_source_registry, resolve_source_paths


def _load_aligned_dataframe(aligned_csv: Path) -> pd.DataFrame:
    frame = pd.read_csv(aligned_csv)
    if "timestamp" not in frame.columns:
        raise ValueError(f"timestamp column not found in aligned CSV: {aligned_csv}")
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame = frame.sort_values("timestamp", kind="stable").drop_duplicates(subset=["timestamp"], keep="last")
    return frame.reset_index(drop=True)


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


def build_direct_data_bundle(config: DirectBenchmarkConfig, experiment_name: str) -> DirectDataBundle:
    registry = build_direct_source_registry()
    spec = registry.get(experiment_name)
    if spec is None:
        raise ValueError(f"Unsupported direct experiment: {experiment_name}")

    source_paths = resolve_source_paths(config.dataset_root, spec)
    if not source_paths:
        raise ValueError(f"No source CSVs configured for {experiment_name}")

    frame = _load_source_dataframe(source_paths[0]) if source_paths[0].name == "flb_input_aligned.csv" else _load_source_dataframe(source_paths[0])
    for source_path in source_paths[1:]:
        frame = _join_additional_source(frame, _load_source_dataframe(source_path))

    missing_columns = [column for column in spec.feature_columns if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Missing feature columns for {experiment_name}: {missing_columns}")

    split_plan = build_split_plan(
        row_count=len(frame),
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        strategy_name=config.split_strategy,
        timestamps=frame["timestamp"].tolist(),
        feature_columns=spec.feature_columns,
        gap_minutes_override=config.split_gap_minutes_override,
    )
    split_frame = _assign_split_labels(frame, split_plan)
    merged_frame, _label_merge_report = merge_event_labels(split_frame, config.event_csv)
    labeled_frame = build_label_frame(merged_frame)
    split_manifest = build_split_manifest(dataframe=labeled_frame, split_plan=split_plan)
    return DirectDataBundle(
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
