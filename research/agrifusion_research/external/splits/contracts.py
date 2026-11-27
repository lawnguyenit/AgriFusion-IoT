from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalSplitConfig:
    canonical_path: Path
    output_root: Path
    timestamp_column: str = "timestamp"
    group_columns: tuple[str, ...] = ()
    shared_timestamp_columns: tuple[str, ...] = ()
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15


@dataclass(frozen=True)
class ExternalSplitResult:
    run_id: str
    output_dir: Path
    splits_path: Path
    row_count: int
    timestamp_block_count: int
