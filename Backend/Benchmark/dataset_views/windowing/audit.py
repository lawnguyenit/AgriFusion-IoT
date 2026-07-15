from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.Benchmark.dataset_views.configs import V2_WINDOW_HORIZONS

from .masking import coerce_boolean_series


def build_initial_audit_store(canonical_df: pd.DataFrame, row_count: int) -> dict[str, list[object]]:
    return build_initial_audit_store_for_horizons(
        canonical_df=canonical_df,
        row_count=row_count,
        horizons=V2_WINDOW_HORIZONS,
    )


def build_initial_audit_store_for_horizons(
    *,
    canonical_df: pd.DataFrame,
    row_count: int,
    horizons,
) -> dict[str, list[object]]:
    audit_store: dict[str, list[object]] = {
        "record.id": canonical_df["record.id"].tolist(),
        "record.node_id": canonical_df["record.node_id"].tolist(),
        "record.ts_sample": canonical_df["record.ts_sample"].tolist(),
        "record.segment_id": canonical_df["record.segment_id"].tolist(),
        "record.continuity_chunk_id": canonical_df["record.continuity_chunk_id"].tolist(),
        "record.continuity_reset_before": coerce_boolean_series(canonical_df["record.continuity_reset_before"]).tolist(),
        "record.continuity_reset_reason": canonical_df["record.continuity_reset_reason"].tolist(),
        "record_id": canonical_df["record.id"].tolist(),
        "timestamp": canonical_df["record.ts_sample"].tolist(),
        "continuity_id": canonical_df["record.continuity_chunk_id"].tolist(),
    }
    for horizon in horizons:
        audit_store[f"{horizon.name}_window_horizon_hours"] = [horizon.hours] * row_count
        audit_store[f"{horizon.name}_expected_observation_count"] = [pd.NA] * row_count
        audit_store[f"{horizon.name}_max_internal_elapsed_gap_sec"] = [pd.NA] * row_count
        audit_store[f"{horizon.name}_continuity_reset_count"] = [pd.NA] * row_count
        audit_store[f"{horizon.name}_window_reset_reason"] = [pd.NA] * row_count
    return audit_store


def summarize_window_audit(
    audit_frame: pd.DataFrame,
    measurement_columns: tuple[str, ...],
) -> dict[str, Any]:
    return summarize_window_audit_for_horizons(
        audit_frame=audit_frame,
        measurement_columns=measurement_columns,
        horizons=V2_WINDOW_HORIZONS,
    )


def summarize_window_audit_for_horizons(
    *,
    audit_frame: pd.DataFrame,
    measurement_columns: tuple[str, ...],
    horizons,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"horizons": {}}
    for horizon in horizons:
        horizon_summary: dict[str, Any] = {
            "window_horizon_hours": int(horizon.hours),
            "expected_observation_count_median": safe_float_median(
                audit_frame[f"{horizon.name}_expected_observation_count"]
            ),
            "max_internal_elapsed_gap_sec_max": safe_int_max(
                audit_frame[f"{horizon.name}_max_internal_elapsed_gap_sec"]
            ),
            "eligible_for_training_rows": int(
                coerce_boolean_series(audit_frame.get(f"{horizon.name}_eligible_for_training", pd.Series(False))).sum()
            ),
            "continuity_reset_rows": int(
                pd.to_numeric(
                    audit_frame[f"{horizon.name}_continuity_reset_count"],
                    errors="coerce",
                ).fillna(0).gt(0).sum()
            ),
            "channels": {},
        }
        for measurement_column in measurement_columns:
            valid_column = f"{measurement_column}__{horizon.name}_valid_observation_count"
            expected_coverage_column = f"{measurement_column}__{horizon.name}_expected_observation_coverage_ratio"
            coverage_column = f"{measurement_column}__{horizon.name}_coverage_ratio"
            span_column = f"{measurement_column}__{horizon.name}_actual_window_span_sec"
            insufficient_column = f"{measurement_column}__{horizon.name}_insufficient_history"
            horizon_summary["channels"][measurement_column] = {
                "median_valid_observation_count": safe_float_median(audit_frame[valid_column]),
                "mean_expected_observation_coverage_ratio": safe_float_mean(audit_frame[expected_coverage_column]),
                "mean_span_coverage_ratio": safe_float_mean(audit_frame[coverage_column]),
                "median_actual_window_span_sec": safe_float_median(audit_frame[span_column]),
                "insufficient_history_rows": int(coerce_boolean_series(audit_frame[insufficient_column]).sum()),
            }
        summary["horizons"][horizon.name] = horizon_summary
    return summary


def safe_float_median(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.median())


def safe_float_mean(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.mean())


def safe_int_max(series: pd.Series) -> int | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return int(numeric.max())
