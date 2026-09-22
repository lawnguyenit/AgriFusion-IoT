from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IntakeConfig:
    source_csv: Path
    old_canonical_csv: Path
    output_root: Path


@dataclass(frozen=True)
class IntakeResult:
    run_id: str
    output_dir: Path
    source_row_count: int
    candidate_row_count: int
    old_row_count: int
    shared_key_count: int
    new_only_key_count: int
    old_only_key_count: int
    report_path: Path
