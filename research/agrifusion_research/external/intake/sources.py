from __future__ import annotations

import urllib.request
from pathlib import Path

from agrifusion_research.external.datasets import REGISTRY, get_dataset_profile
from agrifusion_research.external.profile_types import SourceFileSpec


SOURCE_FILES: dict[str, tuple[SourceFileSpec, ...]] = {
    dataset_id: profile.source_files for dataset_id, profile in REGISTRY.items()
}
DATASET_METADATA: dict[str, dict[str, str]] = {
    dataset_id: dict(profile.metadata) for dataset_id, profile in REGISTRY.items()
}


def download_bytes(url: str, *, timeout_seconds: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AgriFusion-IoT benchmark intake"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def validate_dataset_id(dataset_id: str) -> None:
    get_dataset_profile(dataset_id)
