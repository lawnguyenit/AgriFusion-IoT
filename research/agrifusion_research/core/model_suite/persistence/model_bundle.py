from __future__ import annotations

import json
from pathlib import Path


def write_metrics_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, allow_nan=True),
        encoding="utf-8",
    )
