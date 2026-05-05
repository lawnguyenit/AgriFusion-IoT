from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

WINDOW_DAYS = 5
MAX_SHT_STALE_SEC = 3600
MAX_NPK_STALE_SEC = 3600
MAX_METEO_STALE_SEC = 3 * 3600
TAU_HOURS = {
    "water_pressure": 12.0,
    "heat_pressure": 24.0,
    "dry_air_pressure": 18.0,
    "nutrient_context_pressure": 48.0,
    "sensor_uncertainty": 8.0,
}


@dataclass(frozen=True)
class Layer1Record:
    family: str
    ts_server: int
    observed_at_local: str | None
    source_name: str
    source_event_key: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class StreamIndex:
    ts_values: list[int]
    records: list[Layer1Record]


@dataclass(frozen=True)
class FuzzyMaterializationResult:
    input_root: Path
    output_root: Path
    csv_path: Path
    manifest_path: Path
    row_count: int
    anchor_count: int

