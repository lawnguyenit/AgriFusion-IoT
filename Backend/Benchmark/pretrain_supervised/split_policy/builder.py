from __future__ import annotations

import re
from collections.abc import Sequence

from Backend.Benchmark.pretrain_supervised.split_policy.contracts import SplitPlan
from Backend.Benchmark.pretrain_supervised.split_policy.strategies import (
    build_chronological_v1_plan,
    build_chronological_with_gap_plan,
)


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
        return build_chronological_v1_plan(
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
        return build_chronological_with_gap_plan(
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
