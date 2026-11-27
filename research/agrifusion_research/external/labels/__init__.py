"""Auditable weak-label candidate generation for registered external sources."""

from .contracts import ExternalLabelConfig, ExternalLabelResult
from .pipeline import run_external_label_candidates

__all__ = ["ExternalLabelConfig", "ExternalLabelResult", "run_external_label_candidates"]
