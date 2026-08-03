from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhaseAReadinessConfig:
    protocol_registry_run_dir: Path
    canonical_history_path: Path
    canonical_manifest_path: Path
    output_root: Path
    legacy_reference_run_dirs: tuple[Path, ...] = ()
    protocol_stage_id: str = "PHASE_A_AUDIT"
    strict_min_gap_minutes: float = 13.0
    strict_max_gap_minutes: float = 17.0
    window_horizons_hours: tuple[int, ...] = (3, 8)
    persistence_candidates: tuple[int, ...] = (3, 4)


@dataclass(frozen=True)
class PhaseAReadinessResult:
    run_id: str
    output_dir: Path
    overall_status: str
    e1_record_count: int
