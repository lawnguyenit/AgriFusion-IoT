"""External feature profiles; declared per dataset in external/datasets.py."""
from __future__ import annotations

from agrifusion_research.external.datasets import get_dataset_profile
from agrifusion_research.external.profile_types import ExternalFeatureProfile

__all__ = ["ExternalFeatureProfile", "resolve_profile"]


def resolve_profile(dataset_id: str, run_manifest: dict[str, object]) -> ExternalFeatureProfile:
    try:
        return get_dataset_profile(dataset_id).features
    except ValueError as exc:
        raise ValueError(f"No external feature profile is registered for {dataset_id!r}.") from exc
