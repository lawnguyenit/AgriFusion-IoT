"""Compatibility facade for the legacy point label builder."""

from .applicability import build_applicability_frame
from .artifacts import PointLabelArtifacts, build_point_label_artifacts
from .continuity import enrich_point_continuity_features
from .thresholds import ThresholdContext, build_threshold_context

LEGACY_COMPATIBILITY_ONLY = True

__all__ = [
    "PointLabelArtifacts",
    "ThresholdContext",
    "build_applicability_frame",
    "build_point_label_artifacts",
    "build_threshold_context",
    "enrich_point_continuity_features",
]
