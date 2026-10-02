from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFileSpec:
    name: str
    url: str


SOURCE_FILES: dict[str, tuple[SourceFileSpec, ...]] = {
    "stuard_tomato_irrigation_2023": (
        SourceFileSpec(
            "stuard_environmental_data.csv",
            "https://data.mendeley.com/public-files/datasets/35wh56287y/files/a7e4beec-ca68-459b-8574-dc1bf99214dd/file_downloaded",
        ),
        SourceFileSpec(
            "stuard_soil_data.csv",
            "https://data.mendeley.com/public-files/datasets/35wh56287y/files/9cc5e9d8-a54a-488b-80db-35896156e56e/file_downloaded",
        ),
        SourceFileSpec(
            "stuard_water_meter_data.csv",
            "https://data.mendeley.com/public-files/datasets/35wh56287y/files/bd227cef-4611-47c6-9dcd-ca693be36594/file_downloaded",
        ),
    ),
    "uci_air_quality_360": (
        SourceFileSpec(
            "air+quality.zip",
            "https://archive.ics.uci.edu/static/public/360/air+quality.zip",
        ),
    ),
}

DATASET_METADATA: dict[str, dict[str, str]] = {
    "stuard_tomato_irrigation_2023": {
        "title": "IoT-based Dataset of a Tomato Cultivation Under Different Irrigation Regimes",
        "version": "2",
        "doi": "10.17632/35wh56287y.2",
        "article_doi": "10.1016/j.dib.2025.111521",
        "official_landing_page": "https://data.mendeley.com/datasets/35wh56287y/2",
        "license": "CC BY 4.0",
        "citation": "Belli, L., Davoli, L., Oddi, G., Preite, L., Galaverni, M., Ganino, T., & Ferrari, G. (2024). IoT-based Dataset of a Tomato Cultivation Under Different Irrigation Regimes (Version 2) [Data set]. Mendeley Data. https://doi.org/10.17632/35wh56287y.2",
        "source_copy_url": "https://data.mendeley.com/datasets/35wh56287y/2",
    },
    "uci_air_quality_360": {
        "title": "Air Quality",
        "doi": "10.24432/C59K5F",
        "official_landing_page": "https://archive.ics.uci.edu/dataset/360/air+quality",
        "license": "CC BY 4.0",
        "citation": "Vito, S. (2008). Air Quality [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C59K5F.",
        "use_limit": "UCI states research use only; commercial purposes excluded.",
        "source_copy_url": "https://archive.ics.uci.edu/static/public/360/air+quality.zip",
    },
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def download_bytes(url: str, *, timeout_seconds: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AgriFusion-IoT benchmark intake"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def validate_dataset_id(dataset_id: str) -> None:
    if dataset_id not in SOURCE_FILES:
        raise ValueError(f"Unsupported external dataset_id: {dataset_id!r}")
