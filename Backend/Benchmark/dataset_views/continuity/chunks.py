from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def continuity_required_columns() -> tuple[str, ...]:
    return (
        "record.id",
        "record.node_id",
        "record.ts_sample",
        "record.segment_id",
    )


def build_segment_cadence_index(segment_manifest: dict[str, object]) -> dict[str, int]:
    segments = segment_manifest.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Invalid Layer1 segment manifest: expected a 'segments' list.")

    cadence_by_segment: dict[str, int] = {}
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")
        expected_interval = segment.get("expected_interval_sec")
        if not isinstance(segment_id, str):
            continue
        cadence_numeric = pd.to_numeric(pd.Series([expected_interval]), errors="coerce").iloc[0]
        if pd.isna(cadence_numeric):
            raise ValueError(
                f"Invalid expected_interval_sec for segment '{segment_id}' in the Layer1 segment manifest."
            )
        cadence = int(cadence_numeric)
        if cadence <= 0:
            raise ValueError(
                f"Invalid expected_interval_sec for segment '{segment_id}' in the Layer1 segment manifest."
            )
        cadence_by_segment[segment_id] = cadence
    if not cadence_by_segment:
        raise ValueError("Layer1 segment manifest does not contain any usable segment cadence entries.")
    return cadence_by_segment


def attach_continuity_chunks(
    canonical_df: pd.DataFrame,
    *,
    segment_manifest: dict[str, object],
    boundary_columns: Iterable[str],
    threshold_multiplier: float,
) -> pd.DataFrame:
    required = set(continuity_required_columns())
    missing_required = sorted(column for column in required if column not in canonical_df.columns)
    if missing_required:
        raise ValueError(
            "Canonical history is missing required continuity columns: " + ", ".join(missing_required)
        )

    cadence_by_segment = build_segment_cadence_index(segment_manifest)
    working = canonical_df.loc[:, list(required)].copy()
    working["_source_row_position"] = range(len(canonical_df))
    ts_numeric = pd.to_numeric(working["record.ts_sample"], errors="coerce")
    if ts_numeric.isna().any():
        raise ValueError("Continuity chunking requires valid numeric 'record.ts_sample' values.")
    working["record.ts_sample"] = ts_numeric.astype("int64")

    for boundary_column in boundary_columns:
        if boundary_column in canonical_df.columns:
            working[boundary_column] = _coerce_boolean_series(canonical_df[boundary_column])

    chunk_index = pd.Series(0, index=canonical_df.index, dtype="Int64")
    chunk_id = pd.Series(pd.NA, index=canonical_df.index, dtype="string")
    delta_prev_sec = pd.Series(pd.NA, index=canonical_df.index, dtype="Int64")
    reset_before = pd.Series(False, index=canonical_df.index, dtype="boolean")
    reset_reason = pd.Series(pd.NA, index=canonical_df.index, dtype="string")

    ordered = working.sort_values(
        by=["record.node_id", "record.segment_id", "record.ts_sample", "_source_row_position"],
        kind="stable",
    ).reset_index(names="_original_index")

    for (_, segment_id), group in ordered.groupby(["record.node_id", "record.segment_id"], sort=False, dropna=False):
        segment_key = str(segment_id)
        cadence_seconds = cadence_by_segment.get(segment_key)
        if cadence_seconds is None:
            raise ValueError(
                "Continuity chunking is missing segment cadence for "
                f"segment '{segment_key}' in the Layer1 segment manifest."
            )
        threshold_seconds = float(cadence_seconds) * float(threshold_multiplier)
        ts_values = pd.to_numeric(group["record.ts_sample"], errors="coerce").astype("int64").to_numpy()
        group_chunk_index = np.zeros(len(group), dtype=int)
        group_delta_prev: list[int | None] = [None] * len(group)
        group_reset_before: list[bool] = [False] * len(group)
        for position in range(1, len(group)):
            delta = int(ts_values[position] - ts_values[position - 1])
            group_delta_prev[position] = delta
            boundary_reason = _resolve_boundary_reset_reason(group, position, boundary_columns)
            gap_break = delta > threshold_seconds
            if boundary_reason is not None or gap_break:
                group_chunk_index[position] = group_chunk_index[position - 1] + 1
                group_reset_before[position] = True
                if boundary_reason is not None:
                    reset_reason.loc[group["_original_index"].iloc[position]] = boundary_reason
                elif gap_break:
                    reset_reason.loc[group["_original_index"].iloc[position]] = "gap_threshold_exceeded"
            else:
                group_chunk_index[position] = group_chunk_index[position - 1]

        for local_position, original_index in enumerate(group["_original_index"].tolist()):
            stable_chunk_index = int(group_chunk_index[local_position]) + 1
            chunk_index.loc[original_index] = stable_chunk_index
            chunk_id.loc[original_index] = f"{segment_key}_chunk_{stable_chunk_index:04d}"
            if group_delta_prev[local_position] is not None:
                delta_prev_sec.loc[original_index] = int(group_delta_prev[local_position])
            reset_before.loc[original_index] = bool(group_reset_before[local_position])

    enriched = canonical_df.copy()
    enriched["record.continuity_chunk_index"] = chunk_index
    enriched["record.continuity_chunk_id"] = chunk_id
    enriched["record.continuity_delta_prev_sec"] = delta_prev_sec
    enriched["record.continuity_reset_before"] = reset_before
    enriched["record.continuity_reset_reason"] = reset_reason
    return enriched


def _resolve_boundary_reset_reason(
    group: pd.DataFrame,
    position: int,
    boundary_columns: Iterable[str],
) -> str | None:
    for boundary_column in boundary_columns:
        if boundary_column not in group.columns:
            continue
        if bool(_coerce_boolean_series(group[boundary_column]).iloc[position]):
            if boundary_column == "record.segment_boundary_before":
                return "segment_boundary"
            if boundary_column == "split.boundary_before":
                return "split_boundary"
            return boundary_column
    return None


def _coerce_boolean_series(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "boolean":
        return series.fillna(False)
    normalized = series.replace({"true": True, "false": False, "True": True, "False": False})
    return normalized.fillna(False).astype(bool)
