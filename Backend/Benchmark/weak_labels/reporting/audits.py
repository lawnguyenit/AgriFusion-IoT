from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators.hashes import dataframe_schema_hash
from Backend.Benchmark.weak_labels.shared.configs import (
    CURRENT_PRIMARY_SCOPE_TASK_IDS,
    LABEL_STATUS_LABELED,
    OPTIONAL_EXPLICIT_TASK_IDS,
    POINT_LABELS,
    PRIMARY_OUTPUT_FILES,
    V2_TEMPORAL_LABELS,
    WEAK_LABELS_PIPELINE_NAME,
    WEAK_LABELS_VERSION,
)
from Backend.Benchmark.weak_labels.shared.helpers import file_sha256, output_hashes


def build_label_registry() -> dict[str, object]:
    tasks = [
        {
            "task_id": "v0_point_train",
            "sample_type": "record",
            "labels": list(POINT_LABELS),
            "scope_role": "PRIMARY_PUBLIC_SCOPE",
            "compatible_feature_views": ["v0_minimal_sensor"],
            "notes": "Point weak labels paired with the current full-snapshot v0 feature contract.",
        },
        {
            "task_id": "v1_point_train",
            "sample_type": "record",
            "labels": list(POINT_LABELS),
            "scope_role": "PRIMARY_PUBLIC_SCOPE",
            "compatible_feature_views": ["v1_sensor_row"],
            "notes": "Point weak labels paired with the current reduced-snapshot v1 feature contract.",
        },
        {
            "task_id": "v2_same_y_3h",
            "sample_type": "record",
            "labels": list(POINT_LABELS),
            "scope_role": "PRIMARY_PUBLIC_SCOPE",
            "compatible_feature_views": ["v2_minimal_sensor_window_3h", "v2_sensor_row_window_3h"],
            "notes": "Same-Y label copy for the current primary 3h temporal scope.",
        },
        {
            "task_id": "v2_same_y_8h",
            "sample_type": "record",
            "labels": list(POINT_LABELS),
            "scope_role": "OPTIONAL_EXPLICIT",
            "compatible_feature_views": ["v2_minimal_sensor_window_8h", "v2_sensor_row_window_8h"],
            "notes": "Same-Y label copy for the optional explicit 8h temporal scope.",
        },
        {
            "task_id": "v2_temporal_3h",
            "sample_type": "record",
            "labels": list(V2_TEMPORAL_LABELS),
            "scope_role": "PRIMARY_PUBLIC_SCOPE",
            "compatible_feature_views": ["v2_minimal_sensor_window_3h", "v2_sensor_row_window_3h"],
            "notes": "Primary temporal weak labels for the 3h scope.",
        },
        {
            "task_id": "v2_temporal_8h",
            "sample_type": "record",
            "labels": list(V2_TEMPORAL_LABELS),
            "scope_role": "OPTIONAL_EXPLICIT",
            "compatible_feature_views": ["v2_minimal_sensor_window_8h", "v2_sensor_row_window_8h"],
            "notes": "Optional explicit temporal weak labels for the 8h scope.",
        },
    ]
    return {
        "pipeline": WEAK_LABELS_PIPELINE_NAME,
        "version": WEAK_LABELS_VERSION,
        "current_primary_scope_task_ids": list(CURRENT_PRIMARY_SCOPE_TASK_IDS),
        "optional_explicit_task_ids": list(OPTIONAL_EXPLICIT_TASK_IDS),
        "tasks": tasks,
        "output_files": list(PRIMARY_OUTPUT_FILES),
    }


def build_current_scope_summary() -> dict[str, object]:
    return {
        "scope_kind": "current_weak_label_scope",
        "primary_public_scope": {
            "task_ids": list(CURRENT_PRIMARY_SCOPE_TASK_IDS),
            "description": "Current benchmark-primary weak-label scope aligned to v0, v1, and v2-3h.",
        },
        "optional_explicit_scope": {
            "task_ids": list(OPTIONAL_EXPLICIT_TASK_IDS),
            "description": "Optional weak-label outputs retained for explicit 8h workflows only.",
        },
        "synchronization_notes": [
            "weak_labels does not consume dataset_views outputs; both lanes read the same frozen Layer1 canonical source.",
            "v0_point_train and v1_point_train share the same point weak-label logic but are published as separate task ids for downstream protocol compatibility.",
            "v2_temporal_3h is primary for the current scope; 8h remains optional explicit output.",
        ],
    }


def build_artifact_guide_markdown() -> str:
    return "\n".join(
        [
            "# Weak Labels Artifact Guide",
            "",
            "## Input",
            "- frozen Layer1 canonical telemetry",
            "- frozen Layer1 feature catalog",
            "- manifest and segment context for continuity-aware labeling",
            "- weak-label runtime config such as threshold mode and run profile",
            "",
            "## This Layer Does",
            "- convert canonical evidence into weak targets and rule traces",
            "- keep technical invalidity and intrinsic eligibility separate from downstream protocol decisions",
            "- publish label provenance for point and V2 tasks",
            "",
            "## Output",
            "- `run_metadata/`: provenance, artifact index, and current-scope summary",
            "- `registries/`: label ontology and dependency registry",
            "- `point/`: point weak labels used by v0 and v1",
            "- `v2/`: same-Y and temporal weak labels for 3h and optional 8h",
            "- `audit/`: tranche-0 label assignment, rule firing, and threshold provenance",
        ]
    )


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


def build_persistent_low_k_support(
    *,
    temporal_evidence_3h: pd.DataFrame,
    temporal_evidence_8h: pd.DataFrame,
    default_k: int,
) -> pd.DataFrame:
    frames = [
        temporal_evidence_3h.assign(task_id="v2_temporal_3h", horizon_name="3h"),
        temporal_evidence_8h.assign(task_id="v2_temporal_8h", horizon_name="8h"),
    ]
    rows: list[dict[str, object]] = []
    for frame in frames:
        if frame.empty:
            continue
        eligible = frame.loc[frame["intrinsic_eligibility"].fillna(False).astype(bool)].copy()
        point_low = eligible.loc[eligible["point_train_label_name"].astype("string") == "low_relative_moisture_point"].copy()
        if point_low.empty:
            rows.append(
                {
                    "task_id": str(frame["task_id"].iloc[0]),
                    "horizon_name": str(frame["horizon_name"].iloc[0]),
                    "k_value": default_k,
                    "is_default_k": True,
                    "eligible_row_count": int(len(eligible)),
                    "eligible_point_low_count": 0,
                    "exact_run_length_count": 0,
                    "persistent_row_count": 0,
                    "insufficient_persistence_count": 0,
                    "max_observed_run_length": 0,
                }
            )
            continue
        run_lengths = point_low["low_run_length_ending_at_point"].fillna(0).astype(int)
        max_k = max(default_k, int(run_lengths.max()))
        task_id = str(frame["task_id"].iloc[0])
        horizon_name = str(frame["horizon_name"].iloc[0])
        for k_value in range(1, max_k + 1):
            rows.append(
                {
                    "task_id": task_id,
                    "horizon_name": horizon_name,
                    "k_value": k_value,
                    "is_default_k": k_value == default_k,
                    "eligible_row_count": int(len(eligible)),
                    "eligible_point_low_count": int(len(point_low)),
                    "exact_run_length_count": int((run_lengths == k_value).sum()),
                    "persistent_row_count": int((run_lengths >= k_value).sum()),
                    "insufficient_persistence_count": int((run_lengths < k_value).sum()),
                    "max_observed_run_length": int(run_lengths.max()),
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


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
        "current_primary_scope_task_ids": list(CURRENT_PRIMARY_SCOPE_TASK_IDS),
        "optional_explicit_task_ids": list(OPTIONAL_EXPLICIT_TASK_IDS),
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
