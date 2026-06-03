from __future__ import annotations

from dataclasses import dataclass


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
