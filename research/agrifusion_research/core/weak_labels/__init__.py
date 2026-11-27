"""Native weak-label public API (phase C engine).

The frozen decision phases A (readiness) and B (contract) live in
experiments/weak_labels_phases since GD5; the engine reads their outputs as files only.
"""
from agrifusion_research.core.weak_labels.lifecycle.phase_c_native import build_native_label_artifacts
from agrifusion_research.core.weak_labels.provenance import build_deterministic_id

__all__ = [
    "build_deterministic_id",
    "build_native_label_artifacts",
]
