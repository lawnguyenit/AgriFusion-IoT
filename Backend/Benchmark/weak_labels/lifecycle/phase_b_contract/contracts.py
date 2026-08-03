from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhaseBConfig:
    phase_a_run_dir: Path
    protocol_registry_run_dir: Path
    canonical_history_path: Path
    output_root: Path
    candidate_analysis_policy: str = "PHASE_A_CANDIDATES_ONLY"


@dataclass(frozen=True)
class PhaseBResult:
    run_id: str
    output_dir: Path
    status: str
    primary_k_review_required: bool
