from __future__ import annotations

import numpy as np
import pandas as pd

from Backend.Benchmark.dataset_views.continuity import attach_continuity_chunks, build_segment_cadence_index
from Backend.Benchmark.dataset_views.configs import (
    V2_BOUNDARY_RESET_COLUMNS,
    V2_CONTINUITY_POLICY_VERSION,
    V2_CONTINUITY_THRESHOLD_MULTIPLIER,
    V2_SENSOR_VALIDITY_COLUMNS,
    V2_WINDOW_HORIZONS,
)

from .audit import build_initial_audit_store_for_horizons, summarize_window_audit_for_horizons
from .contracts import WindowViewArtifacts
from .engine import build_feature_column_names_for_horizons, build_working_frame, materialize_segment_windows
from .masking import build_masked_measurements
from .metadata import build_feature_metadata_for_horizons


REQUIRED_WINDOW_COLUMNS: tuple[str, ...] = (
    "record.id",
    "record.node_id",
    "record.ts_sample",
    "record.segment_id",
    "record.segment_boundary_before",
)


def build_v2_sensor_window_view(
    canonical_df: pd.DataFrame,
    measurement_columns: tuple[str, ...],
    segment_manifest: dict[str, object],
    selected_horizon_names: tuple[str, ...] = (),
) -> WindowViewArtifacts:
    validate_required_columns(canonical_df=canonical_df, measurement_columns=measurement_columns)
    selected_horizons = resolve_selected_horizons(selected_horizon_names)
    cadence_by_segment = build_segment_cadence_index(segment_manifest)
    continuity_df = attach_continuity_chunks(
        canonical_df,
        segment_manifest=segment_manifest,
        boundary_columns=V2_BOUNDARY_RESET_COLUMNS,
        threshold_multiplier=V2_CONTINUITY_THRESHOLD_MULTIPLIER,
    )

    row_count = len(canonical_df)
    masked_measurements = build_masked_measurements(continuity_df, measurement_columns)
    feature_columns = build_feature_column_names_for_horizons(
        measurement_columns=measurement_columns,
        horizons=selected_horizons,
    )
    feature_store: dict[str, list[float]] = {column: [np.nan] * row_count for column in feature_columns}
    for measurement_column in measurement_columns:
        feature_store[measurement_column] = masked_measurements[measurement_column].tolist()

    audit_store = build_initial_audit_store_for_horizons(
        canonical_df=continuity_df,
        row_count=row_count,
        horizons=selected_horizons,
    )
    working = build_working_frame(canonical_df=continuity_df, masked_measurements=masked_measurements)

    for (_, segment_id), group in working.groupby(["record.node_id", "record.segment_id"], sort=False, dropna=False):
        cadence_seconds = cadence_by_segment.get(str(segment_id))
        if cadence_seconds is None:
            raise ValueError(
                "v2_sensor_window segment cadence is missing from the Layer1 segment manifest for "
                f"segment '{segment_id}'."
            )
        materialize_segment_windows(
            group=group.reset_index(drop=True),
            measurement_columns=measurement_columns,
            cadence_seconds=cadence_seconds,
            feature_store=feature_store,
            audit_store=audit_store,
            horizons=selected_horizons,
        )

    feature_frame = pd.DataFrame(feature_store, index=canonical_df.index)
    feature_frame = feature_frame.loc[:, feature_columns].apply(pd.to_numeric, errors="coerce")
    audit_frame = pd.DataFrame(audit_store, index=canonical_df.index).convert_dtypes()
    append_view_level_audit_columns(
        audit_frame=audit_frame,
        masked_measurements=masked_measurements,
        measurement_columns=measurement_columns,
        horizons=selected_horizons,
    )

    manifest_sections = {
        "continuity_policy": {
            "version": V2_CONTINUITY_POLICY_VERSION,
            "threshold_multiplier": V2_CONTINUITY_THRESHOLD_MULTIPLIER,
            "boundary_reset_columns": list(V2_BOUNDARY_RESET_COLUMNS),
            "segment_manifest_segment_count": int(len(cadence_by_segment)),
            "selected_horizons": [horizon.name for horizon in selected_horizons],
            "minimum_span_coverage_ratio": float(min(horizon.min_span_coverage_ratio for horizon in selected_horizons)),
        },
        "audit_artifacts": {
            "row_level_window_quality": "window_quality_audit.parquet",
            "row_level_window_quality_csv": "window_quality_audit.csv",
        },
    }
    quality_sections = {
        "window_policy": manifest_sections["continuity_policy"],
        "window_audit_summary": summarize_window_audit_for_horizons(
            audit_frame=audit_frame,
            measurement_columns=measurement_columns,
            horizons=selected_horizons,
        ),
    }

    return WindowViewArtifacts(
        feature_frame=feature_frame,
        audit_frame=audit_frame,
        feature_metadata=build_feature_metadata_for_horizons(
            measurement_columns=measurement_columns,
            horizons=selected_horizons,
        ),
        manifest_sections=manifest_sections,
        quality_sections=quality_sections,
    )


def validate_required_columns(canonical_df: pd.DataFrame, measurement_columns: tuple[str, ...]) -> None:
    required_columns = set(REQUIRED_WINDOW_COLUMNS)
    required_columns.update(measurement_columns)
    required_columns.update(V2_SENSOR_VALIDITY_COLUMNS.values())
    missing_columns = sorted(column for column in required_columns if column not in canonical_df.columns)
    if missing_columns:
        raise ValueError("Canonical history is missing required V2 window columns: " + ", ".join(missing_columns))


def resolve_selected_horizons(selected_horizon_names: tuple[str, ...]):
    if not selected_horizon_names:
        return V2_WINDOW_HORIZONS
    horizon_index = {horizon.name: horizon for horizon in V2_WINDOW_HORIZONS}
    unknown = [name for name in selected_horizon_names if name not in horizon_index]
    if unknown:
        raise ValueError("Unsupported V2 window horizon(s): " + ", ".join(sorted(unknown)))
    return tuple(horizon_index[name] for name in selected_horizon_names)


def append_view_level_audit_columns(
    *,
    audit_frame: pd.DataFrame,
    masked_measurements: pd.DataFrame,
    measurement_columns: tuple[str, ...],
    horizons,
) -> None:
    current_row_complete = masked_measurements.loc[:, list(measurement_columns)].notna().all(axis=1)
    audit_frame["current_row_complete"] = current_row_complete.astype("boolean")

    for horizon in horizons:
        insufficient_columns = [f"{column}__{horizon.name}_insufficient_history" for column in measurement_columns]
        valid_count_columns = [f"{column}__{horizon.name}_valid_observation_count" for column in measurement_columns]
        span_columns = [f"{column}__{horizon.name}_actual_window_span_sec" for column in measurement_columns]
        coverage_columns = [f"{column}__{horizon.name}_coverage_ratio" for column in measurement_columns]

        any_insufficient = (
            audit_frame.loc[:, insufficient_columns]
            .apply(lambda column: column.fillna(True).astype(bool))
            .any(axis=1)
        )
        min_valid_count = audit_frame.loc[:, valid_count_columns].apply(pd.to_numeric, errors="coerce").min(axis=1)
        min_actual_span = audit_frame.loc[:, span_columns].apply(pd.to_numeric, errors="coerce").min(axis=1)
        min_span_coverage = audit_frame.loc[:, coverage_columns].apply(pd.to_numeric, errors="coerce").min(axis=1)
        eligible = current_row_complete & (~any_insufficient)

        audit_frame[f"{horizon.name}_valid_observation_count"] = min_valid_count
        audit_frame[f"{horizon.name}_actual_window_span_sec"] = min_actual_span
        audit_frame[f"{horizon.name}_span_coverage_ratio"] = min_span_coverage
        audit_frame[f"{horizon.name}_eligible_for_training"] = eligible.astype("boolean")

    if len(horizons) != 1:
        return

    horizon = horizons[0]
    audit_frame["window_horizon_hours"] = audit_frame[f"{horizon.name}_window_horizon_hours"]
    audit_frame["valid_observation_count"] = audit_frame[f"{horizon.name}_valid_observation_count"]
    audit_frame["actual_window_span_sec"] = audit_frame[f"{horizon.name}_actual_window_span_sec"]
    audit_frame["span_coverage_ratio"] = audit_frame[f"{horizon.name}_span_coverage_ratio"]
    audit_frame["max_internal_gap_sec"] = audit_frame[f"{horizon.name}_max_internal_elapsed_gap_sec"]
    audit_frame["window_reset_reason"] = audit_frame[f"{horizon.name}_window_reset_reason"]
    audit_frame["eligible_for_training"] = audit_frame[f"{horizon.name}_eligible_for_training"]
