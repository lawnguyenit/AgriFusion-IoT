from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SplitSegment:
    name: str
    start: int
    stop: int

    @property
    def row_count(self) -> int:
        return int(self.stop - self.start)

    @property
    def slice_obj(self) -> slice:
        return slice(self.start, self.stop)


@dataclass(frozen=True)
class SplitPlan:
    strategy_name: str
    row_count: int
    train_ratio: float
    validation_ratio: float
    test_ratio: float
    segments: tuple[SplitSegment, SplitSegment, SplitSegment]
    gap_minutes: int = 0
    gap_source: str = "none"
    notes: str = ""

    @property
    def split_slices(self) -> dict[str, slice]:
        return {segment.name: segment.slice_obj for segment in self.segments}

    @property
    def split_counts(self) -> dict[str, int]:
        return {segment.name: segment.row_count for segment in self.segments}


def build_split_plan(
    *,
    row_count: int,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    strategy_name: str = "chronological_with_lookback_gap",
    timestamps: Sequence[int] | None = None,
    feature_columns: Sequence[str] | None = None,
    gap_minutes_override: int | None = None,
) -> SplitPlan:
    if strategy_name == "chronological_v1":
        return _build_chronological_v1_plan(
            row_count=row_count,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
        )
    if strategy_name == "chronological_with_lookback_gap":
        if timestamps is None:
            raise ValueError("timestamps are required for chronological_with_lookback_gap.")
        gap_minutes, gap_source = resolve_effective_gap_minutes(
            feature_columns=feature_columns or [],
            gap_minutes_override=gap_minutes_override,
        )
        return _build_chronological_with_gap_plan(
            row_count=row_count,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            timestamps=timestamps,
            gap_minutes=gap_minutes,
            gap_source=gap_source,
        )
    raise ValueError(f"Unsupported split strategy: {strategy_name}")


def resolve_effective_gap_minutes(
    *,
    feature_columns: Sequence[str],
    gap_minutes_override: int | None,
) -> tuple[int, str]:
    if gap_minutes_override is not None:
        if gap_minutes_override < 0:
            raise ValueError("gap_minutes_override must be non-negative.")
        return int(gap_minutes_override), "explicit_override"

    max_hours = 0
    for column in feature_columns:
        for match in re.findall(r"_(\d+)h\b", str(column)):
            max_hours = max(max_hours, int(match))
    return int(max_hours * 60), "feature_lookback_auto"


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


def _build_chronological_v1_plan(
    *,
    row_count: int,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> SplitPlan:
    if row_count < 3:
        raise ValueError("Need at least 3 cleaned rows to create train/validation/test splits.")

    train_end = int(row_count * train_ratio)
    validation_end = train_end + int(row_count * validation_ratio)
    train_end = max(1, min(train_end, row_count - 2))
    validation_end = max(train_end + 1, min(validation_end, row_count - 1))

    return SplitPlan(
        strategy_name="chronological_v1",
        row_count=row_count,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        segments=(
            SplitSegment(name="train", start=0, stop=train_end),
            SplitSegment(name="validation", start=train_end, stop=validation_end),
            SplitSegment(name="test", start=validation_end, stop=row_count),
        ),
        notes="Simple contiguous chronological split without purge gap.",
    )


def _build_chronological_with_gap_plan(
    *,
    row_count: int,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    timestamps: Sequence[int],
    gap_minutes: int,
    gap_source: str,
) -> SplitPlan:
    if row_count < 3:
        raise ValueError("Need at least 3 cleaned rows to create train/validation/test splits.")
    if len(timestamps) != row_count:
        raise ValueError("timestamps length must match row_count.")
    if gap_minutes < 0:
        raise ValueError("gap_minutes must be non-negative.")
    if gap_minutes == 0:
        return _build_chronological_v1_plan(
            row_count=row_count,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
        )

    train_target = int(row_count * train_ratio)
    validation_target = max(1, int(row_count * validation_ratio))
    train_end = max(1, min(train_target, row_count - 2))
    gap_seconds = int(gap_minutes * 60)

    validation_start = _advance_to_gap_boundary(
        timestamps=timestamps,
        anchor_index=train_end - 1,
        candidate_index=train_end,
        gap_seconds=gap_seconds,
    )
    validation_end = min(validation_start + validation_target, row_count - 1)
    if validation_end <= validation_start:
        validation_end = validation_start + 1
    if validation_end >= row_count:
        raise ValueError("Gap-aware split leaves no room for the test segment.")

    test_start = _advance_to_gap_boundary(
        timestamps=timestamps,
        anchor_index=validation_end - 1,
        candidate_index=validation_end,
        gap_seconds=gap_seconds,
    )
    if test_start >= row_count:
        raise ValueError("Gap-aware split leaves no rows for the test segment.")

    validation_segment = SplitSegment(name="validation", start=validation_start, stop=validation_end)
    test_segment = SplitSegment(name="test", start=test_start, stop=row_count)
    if validation_segment.row_count <= 0 or test_segment.row_count <= 0:
        raise ValueError("Gap-aware split produced an empty validation or test segment.")

    return SplitPlan(
        strategy_name="chronological_with_lookback_gap",
        row_count=row_count,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        segments=(
            SplitSegment(name="train", start=0, stop=train_end),
            validation_segment,
            test_segment,
        ),
        gap_minutes=gap_minutes,
        gap_source=gap_source,
        notes="Chronological split with a purge gap derived from schema lookback or explicit override.",
    )


def _advance_to_gap_boundary(
    *,
    timestamps: Sequence[int],
    anchor_index: int,
    candidate_index: int,
    gap_seconds: int,
) -> int:
    if gap_seconds <= 0:
        return candidate_index
    anchor_timestamp = int(timestamps[anchor_index])
    index = candidate_index
    while index < len(timestamps):
        current_timestamp = int(timestamps[index])
        if (current_timestamp - anchor_timestamp) >= gap_seconds:
            return index
        index += 1
    return len(timestamps)
