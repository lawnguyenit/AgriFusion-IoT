from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalLabelConfig:
    canonical_path: Path
    intake_manifest_path: Path
    output_root: Path
    calibration_days: int = 21
    tail_shares: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20)
    tau_minutes: tuple[int, ...] | None = None
    min_gap_cadence_fraction: float | None = None
    max_gap_cadence_fraction: float | None = None
    persistence_basis: str = "observation_count"


@dataclass(frozen=True)
class ExternalLabelResult:
    dataset_id: str
    run_id: str
    output_dir: Path
    candidate_labels_path: Path
    registry_path: Path
    support_audit_path: Path
    row_count: int
    candidate_count: int
