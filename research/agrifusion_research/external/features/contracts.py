from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalFeatureConfig:
    canonical_path: Path
    intake_manifest_path: Path
    output_root: Path
    window_hours: tuple[int, ...] = (3, 8)
    min_window_observations: int = 2


@dataclass(frozen=True)
class ExternalFeatureResult:
    dataset_id: str
    run_id: str
    output_dir: Path
    feature_matrix_path: Path
    registry_path: Path
    row_count: int
    feature_count: int
