from __future__ import annotations

import json
from pathlib import Path


def load_json_yaml(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object root in config file: {path}")
    return payload
