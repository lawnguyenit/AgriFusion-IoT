"""Feature superset materialization for external canonical candidates."""

from .contracts import ExternalFeatureConfig, ExternalFeatureResult
from .pipeline import run_external_feature_processing

__all__ = ["ExternalFeatureConfig", "ExternalFeatureResult", "run_external_feature_processing"]
