"""Compatibility facade for historical V2 task artifacts."""

from .artifacts import V2LabelArtifacts, build_v2_label_artifacts

LEGACY_COMPATIBILITY_ONLY = True

__all__ = ["V2LabelArtifacts", "build_v2_label_artifacts"]
