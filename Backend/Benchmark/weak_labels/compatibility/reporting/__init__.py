"""Legacy reporting helpers retained only for historical compatibility."""

from .audits import (
    build_artifact_guide_markdown,
    build_current_scope_summary,
    build_excluded_samples_audit,
    build_label_dependency_registry,
    build_label_distribution,
    build_label_examples,
    build_label_overlap_matrix,
    build_persistent_low_k_support,
    build_label_registry,
    build_run_manifest,
)
from .tranche0_contracts import build_tranche0_audit_artifacts

LEGACY_COMPATIBILITY_ONLY = True

__all__ = [
    "LEGACY_COMPATIBILITY_ONLY",
    "build_artifact_guide_markdown",
    "build_current_scope_summary",
    "build_excluded_samples_audit",
    "build_label_dependency_registry",
    "build_label_distribution",
    "build_label_examples",
    "build_label_overlap_matrix",
    "build_persistent_low_k_support",
    "build_label_registry",
    "build_run_manifest",
    "build_tranche0_audit_artifacts",
]
