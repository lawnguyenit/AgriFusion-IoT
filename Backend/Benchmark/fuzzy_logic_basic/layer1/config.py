from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    from Backend.Config.path_manager import get_benchmark_path, get_layer1_path
except ImportError:
    from ...Config.path_manager import get_benchmark_path, get_layer1_path


def default_input_root() -> Path:
    return get_layer1_path()


def default_output_root() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "dataset"


@dataclass(frozen=True)
class AlignmentConfig:
    input_root: Path = field(default_factory=default_input_root)
    output_root: Path = field(default_factory=default_output_root)
    anchor_cluster_gap_sec: int = 300
    family_match_tolerance_sec: int = 1200
    ec_model_min_samples: int = 50
    ec_default_slope: float = 0.849334
    ec_default_intercept: float = 113.839755
    ec_residual_warn_ratio: float = 0.18
    ec_residual_critical_ratio: float = 0.33
    ec_consistency_binary_threshold: float = 0.9
    pH_missing_penalty: float = 0.15
    allow_meteo_fallback: bool = False
