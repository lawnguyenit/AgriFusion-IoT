from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels.infrastructure.shared.helpers import resolve_local_timestamp_series


def load_canonical_history(path: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(path).convert_dtypes()
    required = ("record.id", "record.ts_sample", "record.segment_id")
    missing = [column for column in required if column not in dataframe.columns]
    if missing:
        raise ValueError("Canonical history is missing required weak-label columns: " + ", ".join(missing))
    # Evaluation and weak-label code use one timestamp authority.  Layer1's
    # canonical export may expose the local timestamp as either an explicit
    # field or only as the UTC epoch `record.ts_sample`; resolve it through
    # the shared helper instead of making each consumer infer timezone rules.
    dataframe["timestamp_local"] = resolve_local_timestamp_series(dataframe)
    return dataframe


def load_feature_catalog(path: Path) -> pd.DataFrame:
    return pd.read_csv(path).convert_dtypes()


def load_json_payload(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_segment_manifest_path(
    *,
    manifest_path: Path | None,
    segment_manifest_path: Path | None,
) -> Path:
    if segment_manifest_path is not None:
        return segment_manifest_path
    if manifest_path is None:
        raise ValueError("weak_labels requires a Layer1 manifest or an explicit segment_manifest_path.")
    manifest_payload = load_json_payload(manifest_path)
    output_paths = manifest_payload.get("output_paths", {}) if isinstance(manifest_payload, dict) else {}
    candidate = output_paths.get("segment_manifest_path")
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError("Layer1 manifest does not expose output_paths.segment_manifest_path.")
    return Path(candidate).resolve()
