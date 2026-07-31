"""Point-task semantic facade.

The legacy applicability/threshold helpers are exposed here as a temporary
compatibility bridge while callers migrate to the native evidence contract.
"""

from Backend.Benchmark.weak_labels.semantic.point.resolver import resolve_point_assignments
from Backend.Benchmark.weak_labels.semantic.evidence.rules import evaluate_point_rules
from Backend.Benchmark.weak_labels.compatibility.legacy_point import (
    ThresholdContext,
    build_applicability_frame,
    build_point_label_artifacts,
    build_threshold_context,
    enrich_point_continuity_features,
)

evaluate_point_evidence = evaluate_point_rules

__all__ = [
    "ThresholdContext",
    "build_applicability_frame",
    "build_point_label_artifacts",
    "build_threshold_context",
    "enrich_point_continuity_features",
    "evaluate_point_evidence",
    "evaluate_point_rules",
    "resolve_point_assignments",
]
