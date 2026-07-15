from __future__ import annotations

import numpy as np
import pandas as pd

from Backend.Benchmark.dataset_views.configs import V2_WINDOW_HORIZONS

from .masking import coerce_boolean_series


def build_feature_column_names(measurement_columns: tuple[str, ...]) -> tuple[str, ...]:
    return build_feature_column_names_for_horizons(
        measurement_columns=measurement_columns,
        horizons=V2_WINDOW_HORIZONS,
    )


def build_feature_column_names_for_horizons(
    *,
    measurement_columns: tuple[str, ...],
    horizons,
) -> tuple[str, ...]:
    derived: list[str] = list(measurement_columns)
    for measurement_column in measurement_columns:
        for horizon in horizons:
            derived.extend(
                [
                    f"{measurement_column}__{horizon.name}_median",
                    f"{measurement_column}__{horizon.name}_iqr",
                    f"{measurement_column}__{horizon.name}_range",
                    f"{measurement_column}__{horizon.name}_delta",
                    f"{measurement_column}__{horizon.name}_slope_per_hour",
                ]
            )
    return tuple(derived)


def build_working_frame(
    canonical_df: pd.DataFrame,
    masked_measurements: pd.DataFrame,
) -> pd.DataFrame:
    working = canonical_df.loc[:, ["record.id", "record.node_id", "record.ts_sample", "record.segment_id"]].copy()
    working["_source_row_position"] = range(len(canonical_df))
    working["record.continuity_chunk_id"] = canonical_df["record.continuity_chunk_id"].astype("string")
    working["record.continuity_reset_before"] = coerce_boolean_series(canonical_df["record.continuity_reset_before"])
    working["record.continuity_reset_reason"] = canonical_df["record.continuity_reset_reason"].astype("string")
    for measurement_column in masked_measurements.columns:
        working[measurement_column] = masked_measurements[measurement_column]

    ts_numeric = pd.to_numeric(working["record.ts_sample"], errors="coerce")
    if ts_numeric.isna().any():
        raise ValueError("v2_sensor_window requires every canonical row to have a valid numeric 'record.ts_sample'.")
    working["record.ts_sample"] = ts_numeric.astype("int64")
    return working.sort_values(
        by=["record.node_id", "record.segment_id", "record.ts_sample", "_source_row_position"],
        kind="stable",
    ).reset_index(drop=True)


def materialize_segment_windows(
    *,
    group: pd.DataFrame,
    measurement_columns: tuple[str, ...],
    cadence_seconds: int,
    feature_store: dict[str, list[float]],
    audit_store: dict[str, list[object]],
    horizons=V2_WINDOW_HORIZONS,
) -> None:
    ts_samples = pd.to_numeric(group["record.ts_sample"], errors="coerce").astype("int64").to_numpy()
    source_positions = pd.to_numeric(group["_source_row_position"], errors="coerce").astype("int64").to_numpy()
    chunk_ids = group["record.continuity_chunk_id"].astype(str).to_numpy()
    reset_before_flags = coerce_boolean_series(group["record.continuity_reset_before"]).to_numpy(dtype=bool)
    reset_reason_values = group["record.continuity_reset_reason"].fillna("").astype(str).to_numpy()
    measurement_arrays = {
        measurement_column: pd.to_numeric(group[measurement_column], errors="coerce").to_numpy(dtype=float)
        for measurement_column in measurement_columns
    }

    for row_position, source_row_position in enumerate(source_positions):
        current_ts = int(ts_samples[row_position])
        for horizon in horizons:
            window_start_ts = current_ts - horizon.seconds
            candidate_start = row_position
            while (
                candidate_start > 0
                and chunk_ids[candidate_start - 1] == chunk_ids[row_position]
                and ts_samples[candidate_start - 1] >= window_start_ts
            ):
                candidate_start -= 1

            continuity_resets = int(reset_before_flags[candidate_start : row_position + 1].sum())
            candidate_timestamps = ts_samples[candidate_start : row_position + 1]
            expected_observations = max(int(horizon.seconds / cadence_seconds) + 1, 1)
            max_gap = 0
            if len(candidate_timestamps) > 1:
                max_gap = int(np.max(np.diff(candidate_timestamps)))

            audit_store[f"{horizon.name}_expected_observation_count"][source_row_position] = expected_observations
            audit_store[f"{horizon.name}_max_internal_elapsed_gap_sec"][source_row_position] = max_gap
            audit_store[f"{horizon.name}_continuity_reset_count"][source_row_position] = continuity_resets
            audit_store[f"{horizon.name}_window_horizon_hours"][source_row_position] = horizon.hours
            audit_store[f"{horizon.name}_window_reset_reason"][source_row_position] = resolve_window_reset_reason(
                reset_reason_values[candidate_start : row_position + 1]
            )

            for measurement_column in measurement_columns:
                write_channel_window_stats(
                    measurement_column=measurement_column,
                    horizon=horizon,
                    candidate_timestamps=candidate_timestamps,
                    candidate_values=measurement_arrays[measurement_column][candidate_start : row_position + 1],
                    current_value=measurement_arrays[measurement_column][row_position],
                    source_row_position=int(source_row_position),
                    expected_observations=expected_observations,
                    feature_store=feature_store,
                    audit_store=audit_store,
                )


def write_channel_window_stats(
    *,
    measurement_column: str,
    horizon,
    candidate_timestamps: np.ndarray,
    candidate_values: np.ndarray,
    current_value: float,
    source_row_position: int,
    expected_observations: int,
    feature_store: dict[str, list[float]],
    audit_store: dict[str, list[object]],
) -> None:
    horizon_name = horizon.name
    valid_mask = np.isfinite(candidate_values)
    valid_values = candidate_values[valid_mask]
    valid_timestamps = candidate_timestamps[valid_mask]
    valid_count = int(valid_mask.sum())
    expected_observation_coverage_ratio = float(valid_count / expected_observations) if expected_observations > 0 else 0.0
    actual_window_span_sec = 0
    if valid_count >= 2:
        actual_window_span_sec = int(valid_timestamps[-1] - valid_timestamps[0])
    span_coverage_ratio = float(actual_window_span_sec / horizon.seconds) if horizon.seconds > 0 else 0.0
    count_requirement_satisfied = valid_count >= horizon.min_valid_observations
    span_requirement_satisfied = span_coverage_ratio >= float(horizon.min_span_coverage_ratio)
    insufficient_history = not (count_requirement_satisfied and span_requirement_satisfied)

    row_count = len(next(iter(feature_store.values())))
    audit_store.setdefault(f"{measurement_column}__{horizon_name}_valid_observation_count", [pd.NA] * row_count)
    audit_store.setdefault(
        f"{measurement_column}__{horizon_name}_expected_observation_coverage_ratio",
        [pd.NA] * row_count,
    )
    audit_store.setdefault(f"{measurement_column}__{horizon_name}_coverage_ratio", [pd.NA] * row_count)
    audit_store.setdefault(f"{measurement_column}__{horizon_name}_actual_window_span_sec", [pd.NA] * row_count)
    audit_store.setdefault(f"{measurement_column}__{horizon_name}_count_requirement_satisfied", [pd.NA] * row_count)
    audit_store.setdefault(f"{measurement_column}__{horizon_name}_span_requirement_satisfied", [pd.NA] * row_count)
    audit_store.setdefault(f"{measurement_column}__{horizon_name}_insufficient_history", [pd.NA] * row_count)
    audit_store[f"{measurement_column}__{horizon_name}_valid_observation_count"][source_row_position] = valid_count
    audit_store[f"{measurement_column}__{horizon_name}_expected_observation_coverage_ratio"][
        source_row_position
    ] = expected_observation_coverage_ratio
    audit_store[f"{measurement_column}__{horizon_name}_coverage_ratio"][source_row_position] = span_coverage_ratio
    audit_store[f"{measurement_column}__{horizon_name}_actual_window_span_sec"][source_row_position] = actual_window_span_sec
    audit_store[f"{measurement_column}__{horizon_name}_count_requirement_satisfied"][
        source_row_position
    ] = count_requirement_satisfied
    audit_store[f"{measurement_column}__{horizon_name}_span_requirement_satisfied"][
        source_row_position
    ] = span_requirement_satisfied
    audit_store[f"{measurement_column}__{horizon_name}_insufficient_history"][source_row_position] = insufficient_history

    median_value = np.nan
    iqr_value = np.nan
    range_value = np.nan
    delta_value = np.nan
    if not insufficient_history:
        median_value = float(np.median(valid_values))
        q75, q25 = np.percentile(valid_values, [75, 25])
        iqr_value = float(q75 - q25)
        range_value = float(np.max(valid_values) - np.min(valid_values))
        if np.isfinite(current_value):
            delta_value = float(current_value - valid_values[0])

    slope_value = np.nan
    slope_evidence_satisfied = (
        valid_count >= horizon.min_slope_observations
        and count_requirement_satisfied
        and span_requirement_satisfied
    )
    if slope_evidence_satisfied:
        slope_value = fit_regression_slope_per_hour(valid_timestamps, valid_values)

    feature_store[f"{measurement_column}__{horizon_name}_median"][source_row_position] = median_value
    feature_store[f"{measurement_column}__{horizon_name}_iqr"][source_row_position] = iqr_value
    feature_store[f"{measurement_column}__{horizon_name}_range"][source_row_position] = range_value
    feature_store[f"{measurement_column}__{horizon_name}_delta"][source_row_position] = delta_value
    feature_store[f"{measurement_column}__{horizon_name}_slope_per_hour"][source_row_position] = slope_value


def fit_regression_slope_per_hour(timestamps: np.ndarray, values: np.ndarray) -> float:
    if len(values) < 3:
        return np.nan
    elapsed_hours = (timestamps - timestamps[0]) / 3600.0
    if np.allclose(elapsed_hours, elapsed_hours[0]):
        return 0.0
    centered_x = elapsed_hours - elapsed_hours.mean()
    variance = float(np.dot(centered_x, centered_x))
    if variance <= 1e-12:
        return 0.0
    centered_y = values - values.mean()
    covariance = float(np.dot(centered_x, centered_y))
    return covariance / variance


def resolve_window_reset_reason(reset_reasons: np.ndarray) -> object:
    for reason in reset_reasons:
        normalized = str(reason).strip()
        if normalized:
            return normalized
    return pd.NA
