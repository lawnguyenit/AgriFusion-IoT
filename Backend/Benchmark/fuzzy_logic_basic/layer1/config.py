from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    from Backend.Config.paths import BACKEND_PATHS
except ImportError:
    from ...Config.paths import BACKEND_PATHS


def default_input_root() -> Path:
    return BACKEND_PATHS.layer1_dir


def default_output_root() -> Path:
    return BACKEND_PATHS.benchmark_dir / "fuzzy_logic_basic" / "dataset"


@dataclass(frozen=True)
class AlignmentConfig:
    input_root: Path = field(default_factory=default_input_root)
    output_root: Path = field(default_factory=default_output_root)
    anchor_cluster_gap_sec: int = 300
    family_match_tolerance_sec: int = 1200
    pH_missing_penalty: float = 0.15
    allow_meteo_fallback: bool = False
