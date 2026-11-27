"""External label profiles; declared per dataset in external/datasets.py."""
from __future__ import annotations

from agrifusion_research.external.datasets import REGISTRY, get_dataset_profile
from agrifusion_research.external.profile_types import ExternalLabelProfile, TargetSpec

PROFILES: dict[str, ExternalLabelProfile] = {dataset_id: profile.labels for dataset_id, profile in REGISTRY.items()}

__all__ = ["PROFILES", "ExternalLabelProfile", "TargetSpec", "resolve_profile"]


def resolve_profile(dataset_id: str) -> ExternalLabelProfile:
    try:
        return get_dataset_profile(dataset_id).labels
    except ValueError as exc:
        raise ValueError(f"No external label profile is registered for {dataset_id!r}.") from exc
