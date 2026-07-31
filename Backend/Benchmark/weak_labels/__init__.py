"""Weak-label public API.

The lifecycle/semantic namespaces are the new implementation boundary. The
flattened builder remains exported for backwards compatibility only.
"""

from Backend.Benchmark.weak_labels.compatibility.legacy_runtime import (
    WeakLabelsConfig,
    WeakLabelsResult,
    build_weak_labels,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_a_readiness import build_phase_a_readiness
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract import (
    build_phase_b_decision_pack,
    freeze_semantic_contract,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_c_native import build_native_label_artifacts
from Backend.Benchmark.weak_labels.provenance import build_deterministic_id

LEGACY_API = True

__all__ = [
    "LEGACY_API",
    "WeakLabelsConfig",
    "WeakLabelsResult",
    "build_deterministic_id",
    "build_native_label_artifacts",
    "build_phase_a_readiness",
    "build_phase_b_decision_pack",
    "build_weak_labels",
    "freeze_semantic_contract",
]
