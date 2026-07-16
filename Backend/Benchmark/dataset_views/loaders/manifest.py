from __future__ import annotations

import json
from pathlib import Path


def load_layer1_manifest(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
