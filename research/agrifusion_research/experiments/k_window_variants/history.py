from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


HISTORY_HORIZON_SECONDS = 3 * 60 * 60
DEFAULT_MAX_LAGS = 12


@dataclass(frozen=True)
class FeatureBundle:
    frame: pd.DataFrame
    feature_names: list[str]
    metadata: dict[str, object]


def build_causal_history_bundle(
    *,
    snapshot_frame: pd.DataFrame,
    snapshot_feature_names: list[str],
    window_frame: pd.DataFrame,
    window_feature_names: list[str],
    row_index: pd.DataFrame,
    max_lags: int = DEFAULT_MAX_LAGS,
) -> FeatureBundle:
    """Add ordered, strictly-past sensor lags to the materialized 3h view.

    The existing 3h view contains causal aggregate statistics, but not the
    order of the observations that produced those statistics. This additive
    representation preserves the existing window features and appends lags
    and structural history-quality values. It never reads labels, target
    lineage, future rows, or eventual run information.
    """

    if max_lags < 1:
        raise ValueError("max_lags must be positive")
    _validate_feature_inputs(snapshot_frame, snapshot_feature_names, window_frame, window_feature_names, row_index)

    ordered = row_index.loc[:, [
        "record.id", "record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"
    ]].copy()
    ordered = ordered.rename(columns={"record.id": "sample_id"})
    ordered["sample_id"] = ordered["sample_id"].astype("string")
    ordered["record.node_id"] = ordered["record.node_id"].astype("string")
    ordered["record.segment_id"] = ordered["record.segment_id"].astype("string")
    ordered["record.ts_sample"] = pd.to_numeric(ordered["record.ts_sample"], errors="coerce")
    if ordered["record.ts_sample"].isna().any():
        raise ValueError("Causal history requires numeric timestamps for every row.")
    ordered = ordered.sort_values(
        ["record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"],
        kind="stable",
    ).reset_index(drop=True)
    if ordered["sample_id"].duplicated().any():
        raise ValueError("Causal history row index must be unique by sample_id.")

    snapshot = snapshot_frame.set_index("sample_id", drop=False).loc[ordered["sample_id"].tolist()]
    window = window_frame.set_index("sample_id", drop=False).loc[ordered["sample_id"].tolist()]
    output = window.loc[:, window_feature_names].copy().reset_index(drop=True)
    output.insert(0, "sample_id", ordered["sample_id"].tolist())

    snapshot_values = snapshot.loc[:, snapshot_feature_names].apply(pd.to_numeric, errors="coerce")
    lag_values: dict[str, list[float]] = {
        f"{feature}__causal_lag_{lag}": [np.nan] * len(ordered)
        for feature in snapshot_feature_names
        for lag in range(1, max_lags + 1)
    }
    lag_ages: dict[str, list[float]] = {
        f"causal_history__lag_{lag}_age_hours": [np.nan] * len(ordered)
        for lag in range(1, max_lags + 1)
    }
    quality: dict[str, list[float]] = {
        "causal_history__3h_prior_row_count": [0.0] * len(ordered),
        "causal_history__3h_prior_valid_row_count": [0.0] * len(ordered),
        "causal_history__3h_prior_span_hours": [0.0] * len(ordered),
        "causal_history__3h_max_internal_gap_hours": [0.0] * len(ordered),
        "causal_history__3h_missing_lag_count": [float(max_lags)] * len(ordered),
    }

    for _, group in ordered.groupby(["record.node_id", "record.segment_id"], sort=False, dropna=False):
        positions = group.index.to_numpy(dtype=int)
        timestamps = ordered.loc[positions, "record.ts_sample"].to_numpy(dtype=np.int64)
        for local_position, output_position in enumerate(positions):
            current_ts = int(timestamps[local_position])
            prior_positions = positions[:local_position]
            prior_timestamps = timestamps[:local_position]
            eligible_mask = prior_timestamps >= current_ts - HISTORY_HORIZON_SECONDS
            prior_positions = prior_positions[eligible_mask]
            prior_timestamps = prior_timestamps[eligible_mask]
            quality["causal_history__3h_prior_row_count"][output_position] = float(len(prior_positions))
            if len(prior_positions):
                quality["causal_history__3h_prior_span_hours"][output_position] = float(
                    (current_ts - int(prior_timestamps[0])) / 3600.0
                )
                all_timestamps = np.concatenate([prior_timestamps, np.asarray([current_ts], dtype=np.int64)])
                quality["causal_history__3h_max_internal_gap_hours"][output_position] = float(
                    np.max(np.diff(all_timestamps)) / 3600.0
                ) if len(all_timestamps) > 1 else 0.0
                prior_ids = ordered.loc[prior_positions, "sample_id"].tolist()
                prior_values = snapshot_values.loc[prior_ids]
                quality["causal_history__3h_prior_valid_row_count"][output_position] = float(
                    prior_values.notna().all(axis=1).sum()
                )

            for lag in range(1, max_lags + 1):
                if len(prior_positions) < lag:
                    continue
                prior_position = int(prior_positions[-lag])
                prior_id = str(ordered.loc[prior_position, "sample_id"])
                age_hours = (current_ts - int(ordered.loc[prior_position, "record.ts_sample"])) / 3600.0
                lag_ages[f"causal_history__lag_{lag}_age_hours"][output_position] = float(age_hours)
                quality["causal_history__3h_missing_lag_count"][output_position] -= 1.0
                for feature in snapshot_feature_names:
                    lag_values[f"{feature}__causal_lag_{lag}"][output_position] = _finite_or_nan(
                        snapshot_values.loc[prior_id, feature]
                    )

    output = pd.concat(
        [
            output,
            pd.DataFrame(lag_values, index=output.index),
            pd.DataFrame(lag_ages, index=output.index),
            pd.DataFrame(quality, index=output.index),
        ],
        axis=1,
    )

    feature_names = [column for column in output.columns if column != "sample_id"]
    output.loc[:, feature_names] = output.loc[:, feature_names].apply(pd.to_numeric, errors="coerce")
    return FeatureBundle(
        frame=output.convert_dtypes(),
        feature_names=feature_names,
        metadata={
            "representation": "causal_history_enriched_3h",
            "base_window_feature_count": len(window_feature_names),
            "snapshot_feature_count": len(snapshot_feature_names),
            "max_lags": max_lags,
            "horizon_seconds": HISTORY_HORIZON_SECONDS,
            "future_used": False,
            "target_derived_features": False,
        },
    )


def _validate_feature_inputs(
    snapshot_frame: pd.DataFrame,
    snapshot_feature_names: list[str],
    window_frame: pd.DataFrame,
    window_feature_names: list[str],
    row_index: pd.DataFrame,
) -> None:
    for frame, name in ((snapshot_frame, "snapshot"), (window_frame, "window")):
        if "sample_id" not in frame.columns or frame["sample_id"].duplicated().any():
            raise ValueError(f"{name} feature frame must have unique sample_id values.")
    missing_snapshot = sorted(set(snapshot_feature_names).difference(snapshot_frame.columns))
    missing_window = sorted(set(window_feature_names).difference(window_frame.columns))
    if missing_snapshot or missing_window:
        raise ValueError(f"Feature frame columns are incomplete: snapshot={missing_snapshot}, window={missing_window}")
    required_row_index = {"record.id", "record.node_id", "record.segment_id", "record.ts_sample", "source_row_position"}
    missing_row_index = sorted(required_row_index.difference(row_index.columns))
    if missing_row_index:
        raise ValueError(f"Row index is missing causal history columns: {missing_row_index}")
    snapshot_ids = set(snapshot_frame["sample_id"].astype("string"))
    window_ids = set(window_frame["sample_id"].astype("string"))
    row_ids = set(row_index["record.id"].astype("string"))
    if snapshot_ids != window_ids or snapshot_ids != row_ids:
        raise ValueError("Snapshot, window, and row-index sample universes must be identical.")


def _finite_or_nan(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan
    return numeric if np.isfinite(numeric) else np.nan
