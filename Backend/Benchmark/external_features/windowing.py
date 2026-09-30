from __future__ import annotations

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
    required = {"sample_id", profile.timestamp_column, *profile.group_columns, *profile.value_columns}
    missing = sorted(required - set(canonical.columns))
    if missing:
        raise ValueError(f"Canonical source is missing feature-processing columns: {missing}")
    source = canonical.copy().reset_index(drop=True)
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
    quality_rows: list[dict[str, object]] = []
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
                    "missing_count": int(values[column].isna().sum()),
                    "missing_fraction": float(values[column].isna().mean()) if len(values) else 0.0,
                }
            )
    feature = feature.convert_dtypes()
    return feature, group_columns, pd.DataFrame(quality_rows).convert_dtypes()
