from __future__ import annotations

from typing import Any

import pandas as pd

from Backend.Benchmark.pretrain_supervised.split_policy.contracts import SplitPlan


def build_split_manifest(
    *,
    dataframe: pd.DataFrame,
    split_plan: SplitPlan,
    timestamp_column: str = "timestamp",
) -> dict[str, Any]:
    manifest_segments: list[dict[str, Any]] = []
    excluded_ranges: list[dict[str, Any]] = []
    previous_stop = 0
    for segment in split_plan.segments:
        if segment.start > previous_stop:
            excluded_ranges.append(
                {
                    "start_index": previous_stop,
                    "stop_index": segment.start,
                    "row_count": int(segment.start - previous_stop),
                    "reason": "purge_gap",
                }
            )
        segment_frame = dataframe.iloc[segment.start:segment.stop]
        if segment_frame.empty:
            timestamp_start = None
            timestamp_end = None
        else:
            timestamp_start = int(segment_frame[timestamp_column].iloc[0]) if timestamp_column in segment_frame.columns else None
            timestamp_end = int(segment_frame[timestamp_column].iloc[-1]) if timestamp_column in segment_frame.columns else None
        manifest_segments.append(
            {
                "name": segment.name,
                "start_index": segment.start,
                "stop_index": segment.stop,
                "row_count": segment.row_count,
                "timestamp_start": timestamp_start,
                "timestamp_end": timestamp_end,
            }
        )
        previous_stop = segment.stop
    if previous_stop < split_plan.row_count:
        excluded_ranges.append(
            {
                "start_index": previous_stop,
                "stop_index": split_plan.row_count,
                "row_count": int(split_plan.row_count - previous_stop),
                "reason": "tail_excluded",
            }
        )

    return {
        "strategy_name": split_plan.strategy_name,
        "row_count": split_plan.row_count,
        "train_ratio": split_plan.train_ratio,
        "validation_ratio": split_plan.validation_ratio,
        "test_ratio": split_plan.test_ratio,
        "gap_minutes": split_plan.gap_minutes,
        "gap_source": split_plan.gap_source,
        "excluded_row_count": int(sum(item["row_count"] for item in excluded_ranges)),
        "excluded_ranges": excluded_ranges,
        "notes": split_plan.notes,
        "segments": manifest_segments,
    }
