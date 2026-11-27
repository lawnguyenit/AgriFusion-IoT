from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalIntakeConfig:
    dataset_id: str
    input_dir: Path | None
    raw_root: Path
    processed_root: Path
    download: bool = False
    release_id: str | None = None


@dataclass(frozen=True)
class ExternalIntakeResult:
    dataset_id: str
    run_id: str
    raw_dir: Path
    output_dir: Path
    canonical_path: Path
    manifest_path: Path
    row_count: int
    excluded_row_count: int
