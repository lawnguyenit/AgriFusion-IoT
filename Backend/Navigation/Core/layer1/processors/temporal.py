from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

import pandas as pd

try:
    from Config.runtime import BACKEND_SETTINGS
except ModuleNotFoundError:
    from ....Config.runtime import BACKEND_SETTINGS

from ..contracts import TemporalSettings
from .common import as_int_from_pd


def apply_temporal_features(
    canonical_df: pd.DataFrame,
    temporal_settings: TemporalSettings,
) -> tuple[pd.DataFrame, int, list[dict[str, object]]]:
    if canonical_df.empty:
        return canonical_df, 0, []

    dataframe = canonical_df.copy()
    order_sample = pd.to_numeric(dataframe["record.ts_sample"], errors="coerce")
    order_server = pd.to_numeric(dataframe["record.ts_server"], errors="coerce")
    dataframe["_order_ts"] = order_sample.fillna(order_server)
    dataframe = dataframe.sort_values(
        ["record.node_id", "_order_ts", "record.event_key"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    _assign_segment_membership(dataframe, temporal_settings)
    expected_interval_by_segment = _estimate_segment_expected_intervals(
        dataframe,
        temporal_settings,
    )
    _finalize_segment_temporal_features(
        dataframe,
        temporal_settings,
        expected_interval_by_segment,
    )

    dataframe = dataframe.drop(columns=["_order_ts"])
    duplicate_count = int(dataframe["record.id"].duplicated().sum())
    segment_summaries = _build_segment_summaries(dataframe, expected_interval_by_segment)
    return dataframe, duplicate_count, segment_summaries


def _assign_segment_membership(
    dataframe: pd.DataFrame,
    temporal_settings: TemporalSettings,
) -> None:
    prev_sample_by_node: dict[str, int | None] = {}
    segment_index_by_node: dict[str, int] = {}
    segment_id_by_node: dict[str, str] = {}

    for index, row in dataframe.iterrows():
        node_id = str(row["record.node_id"])
        ts_sample = as_int_from_pd(row["record.ts_sample"])
        ts_server = as_int_from_pd(row["record.ts_server"])
        previous_ts = prev_sample_by_node.get(node_id)

        if ts_sample is not None and ts_server is not None:
            dataframe.at[index, "record.upload_delay_sec"] = ts_server - ts_sample

        if ts_sample is not None:
            local_dt = datetime.fromtimestamp(ts_sample, tz=BACKEND_SETTINGS.timezone)
            hour_fraction = (
                local_dt.hour
                + (local_dt.minute / 60.0)
                + (local_dt.second / 3600.0)
            )
            dataframe.at[index, "record.hour_sin"] = math.sin(
                (2.0 * math.pi * hour_fraction) / 24.0
            )
            dataframe.at[index, "record.hour_cos"] = math.cos(
                (2.0 * math.pi * hour_fraction) / 24.0
            )

        starts_new_segment = previous_ts is None
        if (
            ts_sample is not None
            and previous_ts is not None
            and (ts_sample - previous_ts) > temporal_settings.segment_break_threshold_sec
        ):
            starts_new_segment = True

        if starts_new_segment:
            segment_index = segment_index_by_node.get(node_id, 0) + 1
            segment_index_by_node[node_id] = segment_index
            segment_id_by_node[node_id] = _build_segment_id(node_id, segment_index)
        else:
            segment_index = segment_index_by_node[node_id]

        dataframe.at[index, "record.segment_index"] = segment_index
        dataframe.at[index, "record.segment_id"] = segment_id_by_node[node_id]
        dataframe.at[index, "record.segment_boundary_before"] = bool(starts_new_segment)

        if ts_sample is not None and previous_ts is not None and not starts_new_segment and ts_sample > previous_ts:
            dataframe.at[index, "record.delta_prev_sec"] = ts_sample - previous_ts

        if ts_sample is not None:
            prev_sample_by_node[node_id] = ts_sample


def _estimate_segment_expected_intervals(
    dataframe: pd.DataFrame,
    temporal_settings: TemporalSettings,
) -> dict[str, int]:
    expected_interval_by_segment: dict[str, int] = {}
    for segment_id, segment_df in dataframe.groupby("record.segment_id", dropna=False, sort=False):
        if pd.isna(segment_id):
            continue
        clean_deltas = pd.to_numeric(segment_df["record.delta_prev_sec"], errors="coerce")
        clean_mask = (
            clean_deltas.notna()
            & (clean_deltas > 0)
            & (clean_deltas < temporal_settings.segment_break_threshold_sec)
            & ~segment_df["delivery.is_buffered_replay"].fillna(False).astype(bool)
        )
        clean_values = clean_deltas.loc[clean_mask]
        if clean_values.empty:
            expected_interval = temporal_settings.expected_interval_sec
        else:
            expected_interval = int(round(float(clean_values.median())))
            if expected_interval <= 0:
                expected_interval = temporal_settings.expected_interval_sec
        expected_interval_by_segment[str(segment_id)] = expected_interval
    return expected_interval_by_segment


def _finalize_segment_temporal_features(
    dataframe: pd.DataFrame,
    temporal_settings: TemporalSettings,
    expected_interval_by_segment: dict[str, int],
) -> None:
    for index, row in dataframe.iterrows():
        segment_id = row.get("record.segment_id")
        if pd.isna(segment_id):
            continue
        expected_interval = expected_interval_by_segment[str(segment_id)]
        dataframe.at[index, "record.segment_expected_interval_sec"] = expected_interval

        delta_prev = as_int_from_pd(row.get("record.delta_prev_sec"))
        boundary_before = bool(row.get("record.segment_boundary_before"))
        if boundary_before:
            dataframe.at[index, "record.gap_flag"] = False
            dataframe.at[index, "record.missing_slot_count"] = 0
            continue

        if delta_prev is None:
            dataframe.at[index, "record.missing_slot_count"] = 0
            continue

        dataframe.at[index, "record.gap_flag"] = (
            delta_prev > temporal_settings.gap_threshold_sec
        )
        missing_slot_count = max(round(delta_prev / expected_interval) - 1, 0)
        dataframe.at[index, "record.missing_slot_count"] = missing_slot_count


def _build_segment_summaries(
    dataframe: pd.DataFrame,
    expected_interval_by_segment: dict[str, int],
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    grouped = dataframe.groupby(
        ["record.node_id", "record.segment_id", "record.segment_index"],
        dropna=False,
        sort=False,
    )
    for (node_id, segment_id, segment_index), segment_df in grouped:
        if pd.isna(segment_id):
            continue
        sample_ts = pd.to_numeric(segment_df["record.ts_sample"], errors="coerce").dropna()
        start_ts = int(sample_ts.iloc[0]) if not sample_ts.empty else None
        end_ts = int(sample_ts.iloc[-1]) if not sample_ts.empty else None
        summaries.append(
            {
                "node_id": str(node_id),
                "segment_id": str(segment_id),
                "segment_index": int(segment_index),
                "row_count": int(len(segment_df)),
                "start_ts_sample": start_ts,
                "end_ts_sample": end_ts,
                "start_record_id": segment_df.iloc[0]["record.id"] if len(segment_df) else None,
                "end_record_id": segment_df.iloc[-1]["record.id"] if len(segment_df) else None,
                "expected_interval_sec": expected_interval_by_segment.get(str(segment_id)),
            }
        )
    return summaries


def _build_segment_id(node_id: str, segment_index: int) -> str:
    normalized_node_id = re.sub(r"[^a-z0-9]+", "_", node_id.strip().lower()).strip("_")
    normalized_node_id = normalized_node_id or "node"
    return f"{normalized_node_id}_seg_{segment_index:04d}"
