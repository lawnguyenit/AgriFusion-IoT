"""Phase A: audit-only readiness lane."""

from .contracts import PhaseAReadinessConfig, PhaseAReadinessResult
from .pipeline import build_phase_a_readiness

__all__ = ["PhaseAReadinessConfig", "PhaseAReadinessResult", "build_phase_a_readiness"]
