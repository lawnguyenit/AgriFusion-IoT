from __future__ import annotations

from Backend.Benchmark.pretrain_supervised.split_policy.builder import build_split_plan

def build_split_slices(row_count: int, train_ratio: float, validation_ratio: float) -> dict[str, slice]:
    split_plan = build_split_plan(
        row_count=row_count,
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
        test_ratio=1.0 - train_ratio - validation_ratio,
        strategy_name="chronological_v1",
    )
    return split_plan.split_slices
