from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from Backend.Config.paths import BACKEND_PATHS
    from Backend.Config.storage import read_json
except ImportError:
    from ...Config.paths import BACKEND_PATHS
    from ...Config.storage import read_json


def get_config_root() -> Path:
    return BACKEND_PATHS.benchmark_dir / "fuzzy_logic_basic" / "configs"


def load_config(name: str) -> dict[str, Any]:
    config_path = get_config_root() / name
    payload = read_json(config_path)
    if not isinstance(payload, dict):
        raise FileNotFoundError(f"Invalid or missing config: {config_path}")
    return payload
