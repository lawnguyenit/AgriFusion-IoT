from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Backend.Config.storage import write_json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_stage_report(
    *,
    stage_name: str,
    input_csv: Path,
    output_dir: Path,
    requested_names: list[str],
    results: list[Any],
    notes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "generated_at_utc": utc_now_iso(),
        "stage_name": stage_name,
        "input_csv": str(input_csv.resolve()),
        "output_dir": str(output_dir.resolve()),
        "requested_names": list(requested_names),
        "generated_files": [
            {
                "name": str(result.experiment_name),
                "output_csv": str(result.output_csv),
                "row_count": int(result.row_count),
                "column_count": int(len(result.columns)),
                "columns": list(result.columns),
            }
            for result in results
        ],
        "notes": list(notes or []),
    }


def write_report(report_path: Path, payload: dict[str, object]) -> Path:
    write_json(report_path, payload)
    return report_path
