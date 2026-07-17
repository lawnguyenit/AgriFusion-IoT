from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators.hashes import dataframe_schema_hash
from Backend.Benchmark.weak_labels.shared.configs import (
    LABEL_STATUS_LABELED,
    POINT_LABELS,
    PRIMARY_OUTPUT_FILES,
    V2_TEMPORAL_LABELS,
    V6_BLOCK_LABELS,
    V6_EVENT_LABELS,
    WEAK_LABELS_PIPELINE_NAME,
    WEAK_LABELS_VERSION,
)
from Backend.Benchmark.weak_labels.shared.helpers import file_sha256, output_hashes


def build_label_registry() -> dict[str, object]:
    return {
        "pipeline": WEAK_LABELS_PIPELINE_NAME,
        "version": WEAK_LABELS_VERSION,
        "tasks": [
            {"task_id": "v0_point_train", "sample_type": "record", "labels": list(POINT_LABELS)},
            {"task_id": "v1_point_train", "sample_type": "record", "labels": list(POINT_LABELS)},
            {"task_id": "v2_same_y_3h", "sample_type": "record", "labels": list(POINT_LABELS)},
            {"task_id": "v2_same_y_8h", "sample_type": "record", "labels": list(POINT_LABELS)},
            {"task_id": "v2_temporal_3h", "sample_type": "record", "labels": list(V2_TEMPORAL_LABELS)},
            {"task_id": "v2_temporal_8h", "sample_type": "record", "labels": list(V2_TEMPORAL_LABELS)},
            {"task_id": "v6_event", "sample_type": "event", "labels": list(V6_EVENT_LABELS)},
            {"task_id": "v6_b8_block", "sample_type": "block", "labels": list(V6_BLOCK_LABELS)},
        ],
        "output_files": list(PRIMARY_OUTPUT_FILES),
    }


def build_label_dependency_registry() -> pd.DataFrame:
    rows = [
        {
            "task_id": "v0_point_train",
            "label_name": "low_relative_moisture_point",
            "direct_source_fields": "npk.soil_moisture_pct",
            "proxy_fields": "",
            "notes": "Primary direct point rule uses soil moisture only.",
        },
        {
            "task_id": "v0_point_train",
            "label_name": "unknown_environment_point",
            "direct_source_fields": "sht.temp_c|sht.humidity_pct|npk.ec|npk.soil_moisture_pct",
            "proxy_fields": "",
            "notes": "Unknown point requires positive environmental evidence from direct measurements only.",
        },
        {
            "task_id": "v2_temporal_3h",
            "label_name": "persistent_low_relative_moisture_window",
            "direct_source_fields": "record.id|npk.soil_moisture_pct",
            "proxy_fields": "v2_window_audit",
            "notes": "Temporal persistence reuses point low predicate plus causal low-run ending at anchor.",
        },
        {
            "task_id": "v6_event",
            "label_name": "persistent_low_relative_moisture_event",
            "direct_source_fields": "npk.soil_moisture_pct",
            "proxy_fields": "",
            "notes": "Event persistence is built from maximal valid low runs.",
        },
        {
            "task_id": "v6_b8_block",
            "label_name": "persistent_low_relative_moisture_block",
            "direct_source_fields": "",
            "proxy_fields": "v6_event_overlap",
            "notes": "Block labels are derived from event overlap, not row-majority voting.",
        },
    ]
    return pd.DataFrame(rows).convert_dtypes()


def build_label_distribution(*frames: pd.DataFrame) -> pd.DataFrame:
    distribution_frames: list[pd.DataFrame] = []
    for frame in frames:
        if frame.empty:
            continue
        available = [column for column in ("sample_type", "task_id", "label_name", "label_status", "intrinsic_eligibility") if column in frame.columns]
        grouped = frame.groupby(available, dropna=False, sort=False).size().reset_index(name="row_count")
        distribution_frames.append(grouped)
    if not distribution_frames:
        return pd.DataFrame(columns=["sample_type", "task_id", "label_name", "label_status", "intrinsic_eligibility", "row_count"])
    return pd.concat(distribution_frames, ignore_index=True).convert_dtypes()


def build_label_overlap_matrix(*frames: pd.DataFrame) -> pd.DataFrame:
    record_frames = [
        frame.loc[frame.get("sample_type", pd.Series(dtype="string")).astype("string") == "record", ["sample_id", "task_id", "label_name"]].copy()
        for frame in frames
        if not frame.empty and "sample_id" in frame.columns and "task_id" in frame.columns and "label_name" in frame.columns
    ]
    record_frames = [frame for frame in record_frames if not frame.empty]
    rows: list[dict[str, object]] = []
    for index, left in enumerate(record_frames):
        for right in record_frames[index:]:
            merged = left.merge(right, on="sample_id", how="inner", suffixes=("_left", "_right"))
            if merged.empty:
                continue
            grouped = (
                merged.groupby(["task_id_left", "label_name_left", "task_id_right", "label_name_right"], dropna=False, sort=False)
                .size()
                .reset_index(name="overlap_count")
            )
            rows.extend(grouped.to_dict(orient="records"))
    return pd.DataFrame(rows).convert_dtypes()


def build_excluded_samples_audit(*frames: pd.DataFrame) -> pd.DataFrame:
    excluded_frames = []
    for frame in frames:
        if frame.empty or "label_status" not in frame.columns:
            continue
        mask = frame["label_status"].astype("string") != LABEL_STATUS_LABELED
        if "intrinsic_eligibility" in frame.columns:
            mask = mask | (~frame["intrinsic_eligibility"].fillna(False).astype(bool))
        if mask.any():
            excluded_frames.append(frame.loc[mask].copy())
    if not excluded_frames:
        return pd.DataFrame()
    return pd.concat(excluded_frames, ignore_index=True).convert_dtypes()


def build_label_examples(*frames: pd.DataFrame, sample_size: int = 5) -> pd.DataFrame:
    examples: list[pd.DataFrame] = []
    for frame in frames:
        if frame.empty or "label_name" not in frame.columns or "task_id" not in frame.columns:
            continue
        grouped = frame.groupby(["task_id", "label_name"], dropna=False, sort=False)
        for _, group in grouped:
            examples.append(group.head(sample_size).copy())
    if not examples:
        return pd.DataFrame()
    return pd.concat(examples, ignore_index=True).convert_dtypes()


def build_run_manifest(
    *,
    config_dict: dict[str, object],
    canonical_path: Path,
    feature_catalog_path: Path,
    segment_manifest_path: Path,
    canonical_df: pd.DataFrame,
    output_dir: Path,
    split_manifest: dict[str, object],
    threshold_records: list[dict[str, object]],
) -> dict[str, object]:
    timestamp_series = pd.to_numeric(canonical_df["record.ts_sample"], errors="coerce").dropna()
    return {
        "pipeline": WEAK_LABELS_PIPELINE_NAME,
        "version": WEAK_LABELS_VERSION,
        "config": config_dict,
        "input_hashes": {
            "canonical_history": file_sha256(canonical_path),
            "feature_catalog": file_sha256(feature_catalog_path),
            "segment_manifest": file_sha256(segment_manifest_path),
        },
        "input_row_count": int(len(canonical_df)),
        "date_range": {
            "start_ts_sample": int(timestamp_series.iloc[0]) if not timestamp_series.empty else None,
            "end_ts_sample": int(timestamp_series.iloc[-1]) if not timestamp_series.empty else None,
        },
        "canonical_schema_hash": dataframe_schema_hash(canonical_df),
        "split_manifest": split_manifest,
        "threshold_records": threshold_records,
        "output_hashes": output_hashes(output_dir),
    }
