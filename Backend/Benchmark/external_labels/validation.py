from __future__ import annotations

import numpy as np
import pandas as pd

from .contracts import ExternalLabelConfig
from .profiles import ExternalLabelProfile


def prepare_source(
    source: pd.DataFrame,
    profile: ExternalLabelProfile,
    config: ExternalLabelConfig,
) -> tuple[pd.DataFrame, str, pd.Series, pd.Timestamp, pd.Timestamp]:
    validate_source(source, profile, config)
    working = source.copy()
    working[profile.timestamp_column] = pd.to_datetime(
        working[profile.timestamp_column], errors="coerce"
    )
    if working[profile.timestamp_column].isna().any():
        raise ValueError("Label input has invalid timestamps; intake must resolve these before labeling.")
    source_observed_start = working[profile.timestamp_column].min()
    source_observed_end = working[profile.timestamp_column].max()
    scope_end = (
        pd.Timestamp(profile.scope_end_exclusive)
        if profile.scope_end_exclusive is not None
        else None
    )
    excluded_by_scope = 0
    if scope_end is not None:
        in_scope = working[profile.timestamp_column].lt(scope_end)
        excluded_by_scope = int((~in_scope).sum())
        working = working.loc[in_scope].copy()
        if working.empty:
            raise ValueError("Dataset scope excludes every row from external labeling.")
    for target in profile.targets:
        working[target.measurement_column] = pd.to_numeric(
            working[target.measurement_column], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)
    working["sample_id"] = working["sample_id"].astype("string")
    if working["sample_id"].isna().any() or working["sample_id"].duplicated().any():
        raise ValueError("Label input requires unique, non-null sample_id values.")

    entity_key = "__label_entity"
    if profile.group_columns:
        if working.loc[:, list(profile.group_columns)].isna().any().any():
            raise ValueError("External label groups must be known; missing entities are not pooled.")
        working[entity_key] = working.loc[:, list(profile.group_columns)].astype("string").agg("|".join, axis=1)
    else:
        working[entity_key] = "__single_entity__"
    working = working.sort_values(
        [entity_key, profile.timestamp_column, "sample_id"], kind="stable"
    ).reset_index(drop=True)
    if working.duplicated([entity_key, profile.timestamp_column], keep=False).any():
        raise ValueError("Duplicate timestamps within an external entity need an explicit tie policy.")

    first_time = working[profile.timestamp_column].min()
    calibration_end = first_time + pd.Timedelta(days=config.calibration_days)
    in_calibration = working[profile.timestamp_column].lt(calibration_end)
    if int(in_calibration.sum()) == 0:
        raise ValueError("The requested calibration interval contains no source rows.")
    working.attrs["source_scope"] = {
        "scope_start_inclusive": first_time.isoformat(),
        "scope_end_exclusive": scope_end.isoformat() if scope_end is not None else None,
        "source_observed_start": source_observed_start.isoformat(),
        "source_observed_end": source_observed_end.isoformat(),
        "source_row_count": int(len(source)),
        "included_row_count": int(len(working)),
        "excluded_row_count": excluded_by_scope,
        "scope_exclusion_policy": "timestamp < scope_end_exclusive" if scope_end is not None else "all canonical rows",
    }
    return working, entity_key, in_calibration, first_time, calibration_end


def validate_source(
    source: pd.DataFrame,
    profile: ExternalLabelProfile,
    config: ExternalLabelConfig,
) -> None:
    allowed = {"sample_id", profile.timestamp_column, *profile.group_columns}
    allowed.update(target.measurement_column for target in profile.targets)
    missing = sorted(allowed - set(source.columns))
    if missing:
        raise ValueError(f"External canonical source is missing label fields: {missing}")
    target_sources = {target.measurement_column for target in profile.targets}
    forbidden = [
        column
        for column in source.columns
        if (column.startswith("criterion.") or column.endswith("(GT)")) and column not in target_sources
    ]
    if forbidden:
        raise ValueError(f"Undeclared criterion fields must not enter target generation: {forbidden}")
    if config.calibration_days <= 0:
        raise ValueError("calibration_days must be positive.")
    if not config.tail_shares or any(not 0 < q < 0.5 for q in config.tail_shares):
        raise ValueError("tail_shares must be non-empty proportions strictly between 0 and 0.5.")
    if len(set(config.tail_shares)) != len(config.tail_shares):
        raise ValueError("tail_shares must be unique.")
    if len({int(round(q * 100)) for q in config.tail_shares}) != len(config.tail_shares):
        raise ValueError("tail_shares collide after conversion to candidate IDs.")
    if not config.tau_minutes or any(int(tau) <= 0 for tau in config.tau_minutes):
        raise ValueError("tau_minutes must be non-empty positive durations.")
    if len(set(config.tau_minutes)) != len(config.tau_minutes):
        raise ValueError("tau_minutes must be unique.")
    if config.min_gap_cadence_fraction <= 0 or config.max_gap_cadence_fraction <= config.min_gap_cadence_fraction:
        raise ValueError("Continuity cadence bounds are invalid.")
