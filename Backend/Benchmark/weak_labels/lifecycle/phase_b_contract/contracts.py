from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhaseBConfig:
    phase_a_run_dir: Path
    protocol_registry_run_dir: Path
    canonical_history_path: Path
    output_root: Path
    q_values: tuple[tuple[str, float], ...] = (
        ("Q05", 58.65),
        ("Q10", 59.96),
        ("Q15", 61.127),
        ("Q20", 62.03),
    )
    strict_min_gap_minutes: float = 13.0
    strict_max_gap_minutes: float = 17.0
    primary_candidate_k: int = 3
    window_horizons_hours: tuple[int, ...] = (3, 8)


@dataclass(frozen=True)
class PhaseBResult:
    run_id: str
    output_dir: Path
    status: str
    primary_k_review_required: bool

