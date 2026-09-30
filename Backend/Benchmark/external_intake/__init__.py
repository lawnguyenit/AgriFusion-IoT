"""Source-specific, non-mutating intake for external benchmark datasets."""

from .pipeline import ExternalIntakeConfig, ExternalIntakeResult, run_external_intake

__all__ = ["ExternalIntakeConfig", "ExternalIntakeResult", "run_external_intake"]
