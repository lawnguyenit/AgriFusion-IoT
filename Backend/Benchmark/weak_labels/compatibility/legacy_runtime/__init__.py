"""Compatibility facade for the pre-lifecycle flattened runtime."""

from .contracts import LabelArtifactBundle, ThresholdRecord, WeakLabelsConfig, WeakLabelsResult
from .pipeline import build_weak_labels

LEGACY_COMPATIBILITY_ONLY = True

__all__ = ["LabelArtifactBundle", "ThresholdRecord", "WeakLabelsConfig", "WeakLabelsResult", "build_weak_labels"]
