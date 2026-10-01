from __future__ import annotations

import numpy as np
import pandas as pd

from .profiles import ExternalFeatureProfile


def build_external_feature_matrix(
    *,
    canonical: pd.DataFrame,
    profile: ExternalFeatureProfile,
    window_hours: tuple[int, ...],
    min_window_observations: int,
) -> tuple[pd.DataFrame, dict[str, list[str]], pd.DataFrame]:
    if min_window_observations < 1:
        raise ValueError("min_window_observations must be positive.")
    if any(hours <= 0 for hours in window_hours) or len(set(window_hours)) != len(window_hours):
        raise ValueError("Window horizons must be unique positive integer hours.")
    required = {
        "sample_id", profile.timestamp_column, *profile.group_columns,
        *profile.value_columns, *profile.context_columns,
    }
    missing = sorted(required - set(canonical.columns))
    if missing:
        raise ValueError(f"Canonical source is missing feature-processing columns: {missing}")
    source = canonical.copy().reset_index(drop=True)
    numeric_quality: list[dict[str, object]] = []
    for column in profile.value_columns:
        original = source[column]
        numeric = pd.to_numeric(original, errors="coerce")
        numeric_array = numeric.to_numpy(dtype=float, na_value=np.nan)
        nonfinite = ~np.isfinite(numeric_array) & ~np.isnan(numeric_array)
        parse_failure_count = int((original.notna().to_numpy() & numeric.isna().to_numpy()).sum())
        nonfinite_count = int(nonfinite.sum())
        numeric_quality.append({
            "feature": column,
            "feature_group": "values",
            "source_dtype": str(original.dtype),
            "numeric_dtype": "Float64",
            "missing_count": int(original.isna().sum()) + parse_failure_count + nonfinite_count,
            "missing_fraction": float((original.isna().sum() + parse_failure_count + nonfinite_count) / len(original)) if len(original) else 0.0,
            "parse_failure_count": parse_failure_count,
            "nonfinite_count": nonfinite_count,
        })
        source[column] = numeric.replace([np.inf, -np.inf], pd.NA).astype("Float64")
    source_row_position = list(range(len(source)))
    timestamps = pd.to_datetime(source[profile.timestamp_column], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("Feature processing requires valid timestamps for every canonical row.")
    source[profile.timestamp_column] = timestamps
    identity = [*profile.group_columns, profile.timestamp_column]
    if source.duplicated(identity).any():
        raise ValueError(f"Duplicate timestamp keys are ambiguous for causal windows: {identity}.")
    source = source.assign(_source_row_position=source_row_position).sort_values(
        [*profile.group_columns, profile.timestamp_column, "_source_row_position"], kind="stable"
    ).reset_index(drop=True)
    groups = source.groupby(list(profile.group_columns), dropna=False, sort=False) if profile.group_columns else [(None, source)]

    feature = source.loc[:, ["sample_id", "_source_row_position", *profile.value_columns]].copy()
    feature = feature.rename(columns={"_source_row_position": "source_row_position"})
    group_columns: dict[str, list[str]] = {"values": list(profile.value_columns)}
    if profile.context_columns:
        context = _build_context_features(source, profile)
        feature = feature.merge(context, on="sample_id", how="left", validate="one_to_one")
        group_columns["irrigation_context"] = [column for column in context if column != "sample_id"]
    quality_rows: list[dict[str, object]] = list(numeric_quality)
    for horizon in window_hours:
        window_name = f"window_{horizon}h"
        horizon_columns: list[str] = []
        for value_column in profile.value_columns:
            for statistic in ("mean", "std", "min", "max", "count"):
                horizon_columns.append(f"{value_column}__{horizon}h_{statistic}")
        values = pd.DataFrame(index=source.index, columns=horizon_columns, dtype="float64")
        for _, group in groups:
            group = group.sort_values([profile.timestamp_column, "_source_row_position"], kind="stable")
            indexed = group.set_index(profile.timestamp_column)
            for value_column in profile.value_columns:
                numeric = pd.to_numeric(indexed[value_column], errors="coerce")
                rolling = numeric.rolling(
                    f"{horizon}h",
                    closed="both",
                    min_periods=min_window_observations,
                )
                values.loc[group.index, f"{value_column}__{horizon}h_mean"] = rolling.mean().to_numpy()
                values.loc[group.index, f"{value_column}__{horizon}h_std"] = rolling.std(ddof=0).to_numpy()
                values.loc[group.index, f"{value_column}__{horizon}h_min"] = rolling.min().to_numpy()
                values.loc[group.index, f"{value_column}__{horizon}h_max"] = rolling.max().to_numpy()
                values.loc[group.index, f"{value_column}__{horizon}h_count"] = rolling.count().to_numpy()
        feature = pd.concat([feature, values.reset_index(drop=True)], axis=1)
        group_columns[window_name] = horizon_columns
        for column in horizon_columns:
            quality_rows.append(
                {
                    "feature": column,
                    "feature_group": window_name,
                    "source_dtype": "derived_numeric",
                    "numeric_dtype": str(values[column].dtype),
                    "missing_count": int(values[column].isna().sum()),
                    "missing_fraction": float(values[column].isna().mean()) if len(values) else 0.0,
                    "parse_failure_count": 0,
                    "nonfinite_count": 0,
                }
            )
    feature = feature.convert_dtypes()
    return feature, group_columns, pd.DataFrame(quality_rows).convert_dtypes()


def _build_context_features(source: pd.DataFrame, profile: ExternalFeatureProfile) -> pd.DataFrame:
    """Build the optional causal meter contrast, separate from strict sensor X."""
    if "water_volume_m3" not in profile.context_columns:
        return source.loc[:, ["sample_id", *profile.context_columns]].copy()
    needed = {"water_timestamp", "water_volume_m3", profile.timestamp_column}
    missing = sorted(needed - set(source.columns))
    if missing:
        raise ValueError(f"Canonical source is missing meter lineage columns: {missing}")
    timestamp = pd.to_datetime(source[profile.timestamp_column], errors="coerce")
    meter_time = pd.to_datetime(source["water_timestamp"], errors="coerce")
    aligned = meter_time.notna() & timestamp.notna() & meter_time.le(timestamp)
    result = source.loc[:, ["sample_id"]].copy()
    groups = source.groupby(list(profile.group_columns), dropna=False, sort=False) if profile.group_columns else [(None, source)]
    increments = pd.Series(pd.NA, index=source.index, dtype="Float64")
    for _, group in groups:
        ordered = group.sort_values(["water_timestamp", profile.timestamp_column], kind="stable")
        meter = pd.to_numeric(ordered["water_volume_m3"], errors="coerce")
        delta = meter.diff()
        delta.loc[delta.lt(0)] = pd.NA  # reset/rollover: increment is unknown
        increments.loc[ordered.index] = delta.array
    result["water_volume_increment_m3"] = increments.where(aligned, pd.NA)
    if "water_alignment_age_sec" in profile.context_columns:
        age = pd.to_numeric(source["water_alignment_age_sec"], errors="coerce")
        result["water_alignment_age_sec"] = age.where(aligned, pd.NA)
    return result
