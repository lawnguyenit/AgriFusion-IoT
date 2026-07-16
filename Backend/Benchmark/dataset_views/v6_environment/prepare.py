from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from Backend.Benchmark.dataset_views.configs import (
    V6_GAP_BREAK_SEC,
    V6_OPTIONAL_AUDIT_COLUMNS,
    V6_REQUIRED_COLUMNS,
)


def prepare_environment_records(
    canonical_df: pd.DataFrame,
    *,
    segment_manifest: dict[str, object],
) -> tuple[pd.DataFrame, dict[str, int]]:
    missing = [column for column in V6_REQUIRED_COLUMNS if column not in canonical_df.columns]
    if missing:
        raise ValueError("V6 sequence dataset is missing required canonical columns: " + ", ".join(missing))

    prepared = canonical_df.copy()
    prepared["record.ts_sample"] = pd.to_numeric(prepared["record.ts_sample"], errors="coerce")
    if prepared["record.ts_sample"].isna().any():
        raise ValueError("V6 requires numeric 'record.ts_sample' values.")
    prepared["record.ts_sample"] = prepared["record.ts_sample"].astype("int64")
    prepared["record.segment_index"] = pd.to_numeric(prepared["record.segment_index"], errors="coerce").astype("Int64")
    prepared["record.segment_expected_interval_sec"] = pd.to_numeric(
        prepared["record.segment_expected_interval_sec"],
        errors="coerce",
    ).astype("Float64")
    prepared["timestamp_local"] = pd.to_datetime(prepared["record.sample_time_local"], errors="coerce", utc=True)
    if prepared["timestamp_local"].isna().any():
        prepared.loc[prepared["timestamp_local"].isna(), "timestamp_local"] = pd.to_datetime(
            prepared.loc[prepared["timestamp_local"].isna(), "record.ts_sample"],
            unit="s",
            errors="coerce",
            utc=True,
        )
    if prepared["timestamp_local"].isna().any():
        raise ValueError("V6 could not resolve local timestamps from 'record.sample_time_local' or 'record.ts_sample'.")
    prepared["timestamp_local"] = prepared["timestamp_local"].dt.tz_convert("Asia/Ho_Chi_Minh")
    prepared["sample_day_key"] = prepared["timestamp_local"].dt.strftime("%Y-%m-%d").astype("string")
    prepared["segment_id"] = prepared["record.segment_id"].astype("string")
    prepared["segment_index"] = prepared["record.segment_index"]
    prepared["node_id"] = prepared["record.node_id"].astype("string")
    prepared["source_row_position"] = np.arange(len(prepared), dtype=np.int64)
    prepared = prepared.sort_values(
        ["node_id", "segment_index", "record.ts_sample", "source_row_position"],
        kind="stable",
    ).reset_index(drop=True)

    cadence_by_segment = _resolve_segment_cadence_seconds(prepared, segment_manifest=segment_manifest)
    prepared["continuity_segment_id"] = pd.Series([pd.NA] * len(prepared), dtype="string")
    prepared["continuity_break_before"] = pd.Series([False] * len(prepared), dtype="boolean")
    prepared["continuity_gap_sec"] = pd.Series([pd.NA] * len(prepared), dtype="Float64")

    continuity_counter = 0
    for (_, segment_id), group in prepared.groupby(["node_id", "segment_id"], sort=False, dropna=False):
        ordered_indices = group.index.tolist()
        previous_ts: int | None = None
        previous_index: int | None = None
        for position, index in enumerate(ordered_indices):
            current_ts = int(prepared.loc[index, "record.ts_sample"])
            boundary_before = bool(prepared.loc[index, "record.segment_boundary_before"]) if "record.segment_boundary_before" in prepared.columns else position == 0
            gap_sec = None if previous_ts is None else current_ts - previous_ts
            is_break = position == 0 or boundary_before or (gap_sec is not None and gap_sec > V6_GAP_BREAK_SEC)
            if is_break:
                continuity_counter += 1
            continuity_segment_id = f"{str(segment_id)}_cont_{continuity_counter:04d}"
            prepared.loc[index, "continuity_segment_id"] = continuity_segment_id
            prepared.loc[index, "continuity_break_before"] = bool(is_break and position > 0)
            if gap_sec is not None:
                prepared.loc[index, "continuity_gap_sec"] = float(gap_sec)
            previous_ts = current_ts
            previous_index = index
        del previous_index

    for column in V6_OPTIONAL_AUDIT_COLUMNS:
        if column not in prepared.columns:
            prepared[column] = pd.Series([pd.NA] * len(prepared), index=prepared.index)
    prepared["derived.vpd_kpa"] = _compute_vpd_kpa(prepared["sht.temp_c"], prepared["sht.humidity_pct"])
    return prepared, cadence_by_segment


def _resolve_segment_cadence_seconds(
    prepared_df: pd.DataFrame,
    *,
    segment_manifest: dict[str, object],
) -> dict[str, int]:
    manifest_map: dict[str, int] = {}
    for segment in segment_manifest.get("segments", []):
        segment_id = str(segment.get("segment_id", ""))
        expected = pd.to_numeric(pd.Series([segment.get("expected_interval_sec")]), errors="coerce").iloc[0]
        if segment_id and pd.notna(expected) and float(expected) > 0:
            manifest_map[segment_id] = int(round(float(expected)))

    cadence_map: dict[str, int] = {}
    for segment_id, group in prepared_df.groupby("segment_id", sort=False, dropna=False):
        ordered = group.sort_values("record.ts_sample", kind="stable")
        deltas = pd.to_numeric(ordered["record.ts_sample"], errors="coerce").diff().dropna()
        valid_deltas = deltas.loc[(deltas > 0) & (deltas <= V6_GAP_BREAK_SEC)]
        cadence = pd.NA
        if not valid_deltas.empty:
            cadence = int(round(float(valid_deltas.median())))
        if pd.isna(cadence):
            record_expected = pd.to_numeric(ordered["record.segment_expected_interval_sec"], errors="coerce").dropna()
            if not record_expected.empty:
                cadence = int(round(float(record_expected.iloc[0])))
        if pd.isna(cadence):
            cadence = manifest_map.get(str(segment_id))
        if cadence is None or pd.isna(cadence) or int(cadence) <= 0:
            raise ValueError(f"V6 could not resolve a positive cadence for segment '{segment_id}'.")
        cadence_map[str(segment_id)] = int(cadence)
    return cadence_map


def _compute_vpd_kpa(temp_series: pd.Series, humidity_series: pd.Series) -> pd.Series:
    temp = pd.to_numeric(temp_series, errors="coerce")
    humidity = pd.to_numeric(humidity_series, errors="coerce")
    es = 0.6108 * np.exp(17.27 * temp / (temp + 237.3))
    vpd = es * (1.0 - (humidity / 100.0))
    return pd.Series(vpd, index=temp_series.index, dtype="Float64")
