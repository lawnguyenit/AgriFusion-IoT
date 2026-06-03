from __future__ import annotations

from collections.abc import Sequence

from Backend.Benchmark.pretrain_supervised.split_policy.contracts import SplitPlan, SplitSegment


def build_chronological_v1_plan(
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
        gap_minutes=0,
        gap_source="none",
        notes="Simple contiguous chronological split without purge gap.",
    )


def build_chronological_with_gap_plan(
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
        return build_chronological_v1_plan(
            row_count=row_count,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
        )

    train_target = int(row_count * train_ratio)
    validation_target = int(row_count * validation_ratio)

    train_end = max(1, min(train_target, row_count - 2))
    validation_target = max(1, validation_target)
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
