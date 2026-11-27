from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class FrozenNativeThresholds:
    q10: float
    sensitivity_df: pd.DataFrame
    manifest: dict[str, object]


def load_native_thresholds(native_label_release_dir: Path) -> FrozenNativeThresholds:
    """Read threshold provenance from a native release; never fit thresholds."""
    release_dir = native_label_release_dir.resolve()
    manifest_path = release_dir / "run_metadata" / "label_release_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    threshold_path = release_dir / "audit" / "threshold_registry.csv"
    if not threshold_path.exists():
        raise ValueError("Native release is missing audit/threshold_registry.csv.")
    thresholds = pd.read_csv(threshold_path).convert_dtypes()
    low = thresholds.loc[thresholds["threshold_id"].astype("string").str.startswith("LOW_MOISTURE", na=False)]
    if len(low) != 1:
        raise ValueError("Native release must contain exactly one LOW_MOISTURE threshold.")
    q10 = float(low.iloc[0]["threshold_value"])
    sensitivity = pd.DataFrame(
        [{"threshold_id": "native_frozen_q10", "q05": pd.NA, "q10": q10, "q15": pd.NA, "q20": pd.NA}]
    ).convert_dtypes()
    return FrozenNativeThresholds(q10=q10, sensitivity_df=sensitivity, manifest=manifest)


def build_protocol_config_hash(config_dict: dict[str, object]) -> str:
    encoded = json.dumps(config_dict, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
