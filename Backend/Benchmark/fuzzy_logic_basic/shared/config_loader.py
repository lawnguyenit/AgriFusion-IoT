from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from Backend.Config.IO.io_json import read_json
    from Backend.Config.path_manager import get_benchmark_path
except ImportError:
    from ...Config.IO.io_json import read_json
    from ...Config.path_manager import get_benchmark_path


def get_config_root() -> Path:
    return get_benchmark_path() / "fuzzy_logic_basic" / "configs"


def load_config(name: str) -> dict[str, Any]:
    config_path = get_config_root() / name
    payload = read_json(config_path)
    if not isinstance(payload, dict):
        raise FileNotFoundError(f"Invalid or missing config: {config_path}")
    return payload

