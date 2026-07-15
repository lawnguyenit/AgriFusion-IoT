from __future__ import annotations

import numpy as np
import pandas as pd


_MEASUREMENT_COLUMNS: tuple[str, ...] = (
    "npk.soil_moisture_pct",
    "npk.soil_temp_c",
    "npk.ec",
    "sht.temp_c",
    "sht.humidity_pct",
    "derived.vpd_kpa",
    "npk.ph",
    "npk.n_proxy",
    "npk.p_proxy",
    "npk.k_proxy",
)

_AUDIT_COPY_COLUMNS: tuple[str, ...] = (
    "record.node_id",
    "record.segment_id",
    "record.segment_index",
    "continuity_segment_id",
)


def resample_continuity_segments(
    prepared_df: pd.DataFrame,
    *,
    cadence_by_segment: dict[str, int],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for continuity_segment_id, group in prepared_df.groupby("continuity_segment_id", sort=False, dropna=False):
        ordered = group.sort_values(["record.ts_sample", "source_row_position"], kind="stable").reset_index(drop=True)
        segment_id = str(ordered.loc[0, "record.segment_id"])
        cadence_sec = int(cadence_by_segment[segment_id])
        anchor_ts = int(ordered.loc[0, "record.ts_sample"])
        slot_assignments = _assign_slots(ordered, anchor_ts=anchor_ts, cadence_sec=cadence_sec)
        max_slot_index = max(slot_assignments)
        grid_indices = np.arange(max_slot_index + 1, dtype=np.int64)
        grid_ts = anchor_ts + (grid_indices * cadence_sec)
        local_anchor = ordered.loc[0, "timestamp_local"]
        grid_local = pd.to_datetime(grid_ts, unit="s", utc=True).tz_convert(local_anchor.tz)
        record_by_slot = _choose_record_per_slot(ordered, slot_assignments=slot_assignments, grid_ts=grid_ts)

        observed_frame = pd.DataFrame(index=grid_indices)
        observed_frame["sequence.grid_index"] = grid_indices
        observed_frame["sequence.timestamp_grid"] = grid_ts
        observed_frame["sequence.timestamp_grid_local"] = grid_local
        observed_frame["sequence.timestamp_grid_iso"] = grid_local.strftime("%Y-%m-%dT%H:%M:%S%z").str.replace(
            r"([+-]\d{2})(\d{2})$",
            r"\1:\2",
            regex=True,
        )
        observed_frame["sequence.source_record_id"] = pd.Series([pd.NA] * len(grid_indices), dtype="string")
        observed_frame["sequence.observed_mask"] = pd.Series([False] * len(grid_indices), dtype="boolean")
        observed_frame["sequence.interpolated_mask"] = pd.Series([False] * len(grid_indices), dtype="boolean")
        observed_frame["sequence.missing_mask"] = pd.Series([True] * len(grid_indices), dtype="boolean")
        observed_frame["sequence.time_since_last_observation_sec"] = pd.Series([pd.NA] * len(grid_indices), dtype="Float64")
        observed_frame["sequence.cadence_sec"] = cadence_sec
        observed_frame["record.node_id"] = str(ordered.loc[0, "record.node_id"])
        observed_frame["record.segment_id"] = str(ordered.loc[0, "record.segment_id"])
        observed_frame["record.segment_index"] = ordered.loc[0, "record.segment_index"]
        observed_frame["continuity_segment_id"] = str(ordered.loc[0, "continuity_segment_id"])
        observed_frame["sample_day_key"] = observed_frame["sequence.timestamp_grid_local"].dt.strftime("%Y-%m-%d").astype("string")

        for column in _MEASUREMENT_COLUMNS:
            if column in ordered.columns:
                observed_frame[column] = _empty_series_like(ordered[column], length=len(grid_indices))

        for slot_index, source_row in record_by_slot.items():
            observed_frame.loc[slot_index, "sequence.source_record_id"] = str(source_row["record.id"])
            observed_frame.loc[slot_index, "sequence.observed_mask"] = True
            observed_frame.loc[slot_index, "sequence.missing_mask"] = False
            for column in _MEASUREMENT_COLUMNS:
                if column in source_row.index:
                    observed_frame.loc[slot_index, column] = source_row[column]

        for column in _MEASUREMENT_COLUMNS:
            if column not in observed_frame.columns:
                continue
            numeric = pd.to_numeric(observed_frame[column], errors="coerce")
            interpolated = numeric.interpolate(method="linear", limit_area="inside")
            observed_frame[column] = pd.Series(interpolated, index=observed_frame.index, dtype="Float64")

        observed_mask = observed_frame["sequence.observed_mask"].fillna(False).to_numpy(dtype=bool, copy=False)
        primary_available = (
            observed_frame["npk.soil_moisture_pct"].notna()
            | observed_frame["npk.soil_temp_c"].notna()
            | observed_frame["npk.ec"].notna()
            | observed_frame["sht.temp_c"].notna()
            | observed_frame["sht.humidity_pct"].notna()
        ).to_numpy(dtype=bool, copy=False)
        interpolated_mask = (~observed_mask) & primary_available
        missing_mask = (~observed_mask) & (~primary_available)
        observed_frame["sequence.interpolated_mask"] = pd.Series(interpolated_mask, index=observed_frame.index, dtype="boolean")
        observed_frame["sequence.missing_mask"] = pd.Series(missing_mask, index=observed_frame.index, dtype="boolean")

        last_observed_ts: int | None = None
        for slot_index in observed_frame.index.tolist():
            if bool(observed_frame.loc[slot_index, "sequence.observed_mask"]):
                last_observed_ts = int(observed_frame.loc[slot_index, "sequence.timestamp_grid"])
            if last_observed_ts is not None:
                observed_frame.loc[slot_index, "sequence.time_since_last_observation_sec"] = float(
                    int(observed_frame.loc[slot_index, "sequence.timestamp_grid"]) - last_observed_ts
                )

        rows.extend(observed_frame.reset_index(drop=True).to_dict(orient="records"))
    return pd.DataFrame(rows).convert_dtypes()


def _empty_series_like(source: pd.Series, *, length: int) -> pd.Series:
    dtype_name = str(source.dtype)
    if dtype_name == "string":
        return pd.Series([pd.NA] * length, dtype="string")
    if dtype_name == "boolean":
        return pd.Series([pd.NA] * length, dtype="boolean")
    if dtype_name in {"Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64"}:
        return pd.Series([pd.NA] * length, dtype=dtype_name)
    return pd.Series([np.nan] * length, dtype="Float64")


def _assign_slots(group: pd.DataFrame, *, anchor_ts: int, cadence_sec: int) -> list[int]:
    slot_indices: list[int] = []
    for _, row in group.iterrows():
        slot_index = int(round((int(row["record.ts_sample"]) - anchor_ts) / cadence_sec))
        slot_indices.append(max(slot_index, 0))
    return slot_indices


def _choose_record_per_slot(
    group: pd.DataFrame,
    *,
    slot_assignments: list[int],
    grid_ts: np.ndarray,
) -> dict[int, pd.Series]:
    record_by_slot: dict[int, pd.Series] = {}
    for position, slot_index in enumerate(slot_assignments):
        row = group.iloc[position]
        candidate_error = abs(int(row["record.ts_sample"]) - int(grid_ts[slot_index]))
        existing = record_by_slot.get(slot_index)
        if existing is None:
            record_by_slot[slot_index] = row
            continue
        existing_error = abs(int(existing["record.ts_sample"]) - int(grid_ts[slot_index]))
        if candidate_error < existing_error:
            record_by_slot[slot_index] = row
    return record_by_slot
