from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

try:
    from Backend.Config.IO.io_json import write_json
except ImportError:
    from ...Config.IO.io_json import write_json


def write_outputs(
    rows: list[dict[str, Any]],
    output_root: Path,
    manifest: dict[str, Any],
) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / "layer2_fuzzy.csv"
    manifest_path = output_root / "manifest.json"

    if rows:
        fieldnames = sorted({key for row in rows for key in row.keys()})
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: "|".join(str(item) for item in value) if isinstance(value, list) else value
                        for key, value in row.items()
                    }
                )
    else:
        csv_path.write_text("", encoding="utf-8")

    write_json(manifest_path, manifest)
    return csv_path, manifest_path

