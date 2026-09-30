from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_audit_dir(output_root: Path) -> tuple[str, Path]:
    run_id = "pretrain_audit_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = (output_root / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    return run_id, output_dir


def write_audit_artifacts(
    *,
    output_dir: Path,
    selected_features: pd.DataFrame,
    labels: pd.DataFrame,
    splits: pd.DataFrame,
    feature_quality: pd.DataFrame,
    target_support: pd.DataFrame,
    manifest: dict[str, object],
) -> None:
    paths = {
        "selected_features": output_dir / "selected_features.parquet",
        "selected_labels": output_dir / "selected_labels.parquet",
        "selected_splits": output_dir / "selected_splits.parquet",
        "feature_quality": output_dir / "feature_quality.csv",
        "target_support": output_dir / "target_support.csv",
    }
    selected_features.to_parquet(paths["selected_features"], index=False)
    labels.to_parquet(paths["selected_labels"], index=False)
    splits.to_parquet(paths["selected_splits"], index=False)
    feature_quality.to_csv(paths["feature_quality"], index=False)
    target_support.to_csv(paths["target_support"], index=False)
    manifest["artifacts"] = {
        key: {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "row_count": int(len(pd.read_parquet(path))) if path.suffix == ".parquet" else int(len(pd.read_csv(path))),
        }
        for key, path in paths.items()
    }
    (output_dir / "audit_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
