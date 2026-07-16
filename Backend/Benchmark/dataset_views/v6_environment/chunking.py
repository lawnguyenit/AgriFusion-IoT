from __future__ import annotations

from datetime import timedelta

import pandas as pd

from Backend.Benchmark.dataset_views.configs import (
    V6_CHUNK_HOURS,
    V6_CHUNK_START_HOURS,
    V6_MIN_CHUNK_COVERAGE_RATIO,
)

from .fragments import annotate_chunk_fragments


def build_chunked_sequence_dataset(
    sequence_df: pd.DataFrame,
    *,
    cadence_by_segment: dict[str, int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    chunk_rows: list[dict[str, object]] = []
    updated_frames: list[pd.DataFrame] = []
    fragment_rows: list[dict[str, object]] = []
    for (node_id, segment_id), group in sequence_df.groupby(["record.node_id", "record.segment_id"], sort=False, dropna=False):
        if group.empty:
            continue
        cadence_sec = int(cadence_by_segment[str(segment_id)])
        first_day = group["sequence.timestamp_grid_local"].min().normalize()
        last_day = group["sequence.timestamp_grid_local"].max().normalize()
        current_day = first_day
        while current_day <= last_day:
            for start_hour in V6_CHUNK_START_HOURS:
                chunk_slice, chunk_record = _build_chunk_slice(
                    group=group,
                    node_id=str(node_id),
                    segment_id=str(segment_id),
                    cadence_sec=cadence_sec,
                    current_day=current_day,
                    start_hour=int(start_hour),
                )
                chunk_rows.append(chunk_record)
                if chunk_slice.empty:
                    continue
                chunk_slice = annotate_chunk_fragments(chunk_slice, fragment_rows=fragment_rows)
                updated_frames.append(chunk_slice)
            current_day = current_day + timedelta(days=1)

    sequence_rows_df = pd.concat(updated_frames, ignore_index=True).convert_dtypes() if updated_frames else pd.DataFrame().convert_dtypes()
    chunk_manifest_df = pd.DataFrame(chunk_rows).convert_dtypes()
    discarded_chunks_df = chunk_manifest_df.loc[~chunk_manifest_df["chunk_kept"].fillna(False)].copy()
    event_fragment_registry_df = pd.DataFrame(fragment_rows).convert_dtypes()
    return sequence_rows_df, chunk_manifest_df, discarded_chunks_df, event_fragment_registry_df


def _build_chunk_slice(
    *,
    group: pd.DataFrame,
    node_id: str,
    segment_id: str,
    cadence_sec: int,
    current_day: pd.Timestamp,
    start_hour: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    chunk_start = current_day + timedelta(hours=start_hour)
    chunk_end = chunk_start + timedelta(hours=V6_CHUNK_HOURS)
    chunk_id = f"{segment_id}_{chunk_start.strftime('%Y%m%d')}_{start_hour:02d}"
    chunk_slice = group.loc[
        (group["sequence.timestamp_grid_local"] >= chunk_start)
        & (group["sequence.timestamp_grid_local"] < chunk_end)
    ].copy()
    expected_slot_count = max(int(round((V6_CHUNK_HOURS * 3600) / cadence_sec)), 1)
    usable_slot_count = int((~chunk_slice["sequence.missing_mask"].fillna(True)).sum()) if not chunk_slice.empty else 0
    continuity_ids = chunk_slice["continuity_segment_id"].astype("string").dropna().unique().tolist()
    chunk_contains_break = len(continuity_ids) > 1
    coverage_ratio = round(usable_slot_count / expected_slot_count, 6) if expected_slot_count > 0 else 0.0
    kept, discard_reason = _resolve_chunk_status(
        chunk_slice=chunk_slice,
        chunk_contains_break=chunk_contains_break,
        coverage_ratio=coverage_ratio,
    )

    chunk_record = {
        "chunk_id": chunk_id,
        "record.node_id": node_id,
        "record.segment_id": segment_id,
        "chunk_day_key": chunk_start.strftime("%Y-%m-%d"),
        "chunk_window_label": f"{start_hour:02d}:00-{start_hour + V6_CHUNK_HOURS:02d}:00",
        "chunk_start_local": chunk_start.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + chunk_start.strftime("%z")[-2:],
        "chunk_end_local": chunk_end.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + chunk_end.strftime("%z")[-2:],
        "chunk_kept": kept,
        "discard_reason": discard_reason if not kept else pd.NA,
        "coverage_ratio": coverage_ratio,
        "expected_slot_count": expected_slot_count,
        "usable_slot_count": usable_slot_count,
        "actual_row_count": int(len(chunk_slice)),
        "contains_continuity_break": chunk_contains_break,
    }

    if chunk_slice.empty:
        return chunk_slice, chunk_record

    chunk_slice["chunk_id"] = chunk_id
    chunk_slice["chunk_day_key"] = chunk_start.strftime("%Y-%m-%d")
    chunk_slice["chunk_window_label"] = f"{start_hour:02d}:00-{start_hour + V6_CHUNK_HOURS:02d}:00"
    chunk_slice["chunk_kept"] = kept
    chunk_slice["chunk_discard_reason"] = discard_reason if not kept else pd.NA
    chunk_slice["chunk_coverage_ratio"] = coverage_ratio
    chunk_slice["chunk_expected_slot_count"] = expected_slot_count
    chunk_slice["chunk_timestep_index"] = range(len(chunk_slice))
    return chunk_slice, chunk_record


def _resolve_chunk_status(
    *,
    chunk_slice: pd.DataFrame,
    chunk_contains_break: bool,
    coverage_ratio: float,
) -> tuple[bool, str]:
    if chunk_slice.empty:
        return False, "no_rows"
    if chunk_contains_break:
        return False, "continuity_break"
    if coverage_ratio < V6_MIN_CHUNK_COVERAGE_RATIO:
        return False, "insufficient_coverage"
    return True, ""
