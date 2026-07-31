"""Stable contract type exports for the weak-label lifecycle."""

from Backend.Benchmark.weak_labels.contracts.native import (
    NativeContract,
    NativeContractError,
    NativeEngineConfig,
    NativeEngineResult,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness.contracts import (
    PhaseAReadinessConfig,
    PhaseAReadinessResult,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.contracts import PhaseBConfig, PhaseBResult

__all__ = [
    "NativeContract",
    "NativeContractError",
    "NativeEngineConfig",
    "NativeEngineResult",
    "PhaseAReadinessConfig",
    "PhaseAReadinessResult",
    "PhaseBConfig",
    "PhaseBResult",
]
