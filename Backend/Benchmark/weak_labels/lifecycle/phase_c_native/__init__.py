"""Phase C: contract-gated native semantic engine."""

from Backend.Benchmark.weak_labels.compatibility.differential.audit import build_shadow_differential_audit
from Backend.Benchmark.weak_labels.contracts.native import (
    DifferentialAuditResult,
    NativeContract,
    NativeContractError,
    NativeEngineConfig,
    NativeEngineResult,
    deterministic_id,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_c_native.pipeline import (
    build_native_engine_registry,
    build_native_label_artifacts,
    load_native_contract,
)
from Backend.Benchmark.weak_labels.provenance.materialize import materialize_from_assignments

__all__ = [
    "DifferentialAuditResult",
    "NativeContract",
    "NativeContractError",
    "NativeEngineConfig",
    "NativeEngineResult",
    "build_native_engine_registry",
    "build_native_label_artifacts",
    "build_shadow_differential_audit",
    "deterministic_id",
    "load_native_contract",
    "materialize_from_assignments",
]
