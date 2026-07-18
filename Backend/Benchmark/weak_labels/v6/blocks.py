from __future__ import annotations

import pandas as pd

from Backend.Benchmark.weak_labels.shared.configs import (
    LABEL_STATUS_EXCLUDED_WINDOW,
    LABEL_STATUS_LABELED,
    V6_BLOCK_EXCLUDED_LABEL,
    V6_BLOCK_HOURS,
    V6_BLOCK_LABELS,
    V6_BLOCK_MIN_COVERAGE_RATIO,
    V6_EVENT_LABELS,
)
from Backend.Benchmark.weak_labels.shared.helpers import json_dumps_compact, local_time_bucket


def build_block_composition(
    raw_event_df: pd.DataFrame,
    membership_df: pd.DataFrame,
) -> pd.DataFrame:
    membership_map = membership_df.groupby("record.id", sort=False)["event_label_name"].agg(list).to_dict() if not membership_df.empty else {}
    working = raw_event_df.copy()
    working["block_day"] = working["timestamp_local"].dt.strftime("%Y-%m-%d").astype("string")
    working["block_window_label"] = working["timestamp_local"].apply(local_time_bucket).astype("string")
    working["block_id"] = (
        working["record.segment_id"].astype("string")
        + "_"
        + working["block_day"].astype("string")
        + "_"
        + working["block_window_label"].astype("string")
    )

    rows: list[dict[str, object]] = []
    for block_id, group in working.groupby("block_id", sort=False, dropna=False):
        cadence = int(round(float(pd.to_numeric(group["record.segment_expected_interval_sec"], errors="coerce").dropna().iloc[0])))
        expected_slots = max(int(round((V6_BLOCK_HOURS * 3600) / cadence)), 1)
        base_partitions = sorted(group["base_partition"].astype("string").dropna().unique().tolist())
        continuity_ids = sorted(group["raw_continuity_chunk_id"].astype("string").dropna().unique().tolist())
        event_labels = [label for record_id in group["record.id"].astype("string").tolist() for label in membership_map.get(record_id, [])]

        rows.append(
            {
                "sample_id": str(block_id),
                "sample_type": "block",
                "task_id": "v6_b8_block",
                "record.segment_id": str(group["record.segment_id"].iloc[0]),
                "block_day_key": str(group["block_day"].iloc[0]),
                "block_window_label": str(group["block_window_label"].iloc[0]),
                "base_partition": json_dumps_compact(base_partitions),
                "effective_partition": base_partitions[0] if len(base_partitions) == 1 else "excluded",
                "coverage_ratio": min(float(len(group) / expected_slots), 1.0),
                "expected_slot_count": expected_slots,
                "actual_row_count": int(len(group)),
                "continuity_count": int(len(continuity_ids)),
                "persistent_overlap_count": int(sum(label == V6_EVENT_LABELS[1] for label in event_labels)),
                "unknown_overlap_count": int(sum(label == V6_EVENT_LABELS[2] for label in event_labels)),
                "normal_overlap_count": int(sum(label == V6_EVENT_LABELS[0] for label in event_labels)),
                "overlap_event_labels": json_dumps_compact(sorted(set(event_labels))),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_block_labels(block_composition_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in block_composition_df.itertuples(index=False):
        if float(row.coverage_ratio) < V6_BLOCK_MIN_COVERAGE_RATIO or int(row.continuity_count) > 1 or row.effective_partition == "excluded":
            label_name = V6_BLOCK_EXCLUDED_LABEL
            label_status = LABEL_STATUS_EXCLUDED_WINDOW
            effective_partition = "excluded"
            exclusion_reason = "insufficient_coverage_or_boundary"
        elif int(row.persistent_overlap_count) > 0 and int(row.unknown_overlap_count) == 0:
            label_name = V6_BLOCK_LABELS[1]
            label_status = LABEL_STATUS_LABELED
            effective_partition = row.effective_partition
            exclusion_reason = pd.NA
        elif int(row.unknown_overlap_count) > 0 or (int(row.persistent_overlap_count) > 0 and int(row.unknown_overlap_count) > 0):
            label_name = V6_BLOCK_LABELS[2]
            label_status = LABEL_STATUS_LABELED
            effective_partition = row.effective_partition
            exclusion_reason = pd.NA
        else:
            label_name = V6_BLOCK_LABELS[0]
            label_status = LABEL_STATUS_LABELED
            effective_partition = row.effective_partition
            exclusion_reason = pd.NA
        rows.append(
            {
                "sample_id": row.sample_id,
                "sample_type": row.sample_type,
                "task_id": row.task_id,
                "label_name": label_name,
                "label_status": label_status,
                "base_partition": row.base_partition,
                "effective_partition": effective_partition,
                "exclusion_reason": exclusion_reason,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()
