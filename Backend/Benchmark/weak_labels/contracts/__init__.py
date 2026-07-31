"""Canonical contract facades for the weak-label lifecycle.

This package contains contract types and loading/validation helpers only.  It
does not depend on legacy label builders or dataset-view code.
"""

from Backend.Benchmark.weak_labels.contracts.loaders import load_native_contract
from Backend.Benchmark.weak_labels.contracts.schemas import (
    NativeContract,
    NativeContractError,
    NativeEngineConfig,
    NativeEngineResult,
    PhaseAReadinessConfig,
    PhaseAReadinessResult,
    PhaseBConfig,
    PhaseBResult,
)
from Backend.Benchmark.weak_labels.contracts.validators import validate_contract_namespace

__all__ = [
    "NativeContract",
    "NativeContractError",
    "NativeEngineConfig",
    "NativeEngineResult",
    "PhaseAReadinessConfig",
    "PhaseAReadinessResult",
    "PhaseBConfig",
    "PhaseBResult",
    "load_native_contract",
    "validate_contract_namespace",
]
