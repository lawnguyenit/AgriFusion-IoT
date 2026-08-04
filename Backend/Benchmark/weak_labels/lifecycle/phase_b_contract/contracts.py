from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


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


class PhaseB2Error(ValueError):
    """Raised when a Phase B2 contract cannot be safely frozen."""


@dataclass(frozen=True)
class PhaseB2Config:
    """Explicit inputs for the fail-closed Phase B2 freeze gate."""

    phase_a_run_dir: Path
    phase_b1_decision_pack_dir: Path
    protocol_registry_run_dir: Path
    review_decision_path: Path
    anchor_safety_audit_path: Path
    distribution_audit_path: Path
    derived_evidence_contract_path: Path
    continuity_contract_path: Path
    window_contract_path: Path
    expected_difference_contract_path: Path
    canonical_history_path: Path
    output_root: Path
    # Explicit Q×K×fold selection profile. Keeping this separate from the
    # reviewer decision lets the same semantic review be replayed with a
    # different, predeclared diagnostic matrix.
    selection_config_path: Path | None = None


@dataclass(frozen=True)
class PhaseB2Result:
    run_id: str
    output_dir: Path | None
    status: Literal["CONTRACT_FROZEN", "CONTRACT_FREEZE_BLOCKED"]
    frozen_registry_dir: Path | None = None
    reason: str | None = None
