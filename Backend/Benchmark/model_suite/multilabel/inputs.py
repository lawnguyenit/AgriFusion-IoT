from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_reviewed_audit(
    audit_dir: Path,
    target_columns: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    manifest_path = audit_dir / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("audit_status") != "ready_for_model_policy_review":
        raise ValueError("Multi-label fitting requires a pre-train audit with ready_for_model_policy_review status.")
    if manifest.get("model_fit_performed") is not False:
        raise ValueError("The supplied pre-train audit manifest is not a review-only audit artifact.")
    declared_targets = tuple(manifest.get("target_columns", []))
    if tuple(target_columns) != declared_targets:
        raise ValueError("Requested target columns must exactly match the ordered targets in the pre-train audit.")
    if not target_columns or len(set(target_columns)) != len(target_columns):
        raise ValueError("Select one or more distinct target columns for an independent binary-head run.")
    files: dict[str, Path] = {}
    for key, filename in (
        ("selected_features", "selected_features.parquet"),
        ("selected_labels", "selected_labels.parquet"),
        ("selected_splits", "selected_splits.parquet"),
    ):
        artifact = manifest.get("artifacts", {}).get(key, {})
        path = Path(str(artifact.get("path", audit_dir / filename)))
        if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
            raise ValueError(f"Pre-train audit artifact {key!r} is missing or its checksum is invalid.")
        files[key] = path
    features = pd.read_parquet(files["selected_features"])
    labels = pd.read_parquet(files["selected_labels"])
    splits = pd.read_parquet(files["selected_splits"])
    if "sample_id" not in features or "sample_id" not in labels or "sample_id" not in splits:
        raise ValueError("Audited feature, label, and split files must contain sample_id.")
    features["sample_id"] = features["sample_id"].astype("string")
    labels["sample_id"] = labels["sample_id"].astype("string")
    splits["sample_id"] = splits["sample_id"].astype("string")
    if features["sample_id"].duplicated().any() or labels["sample_id"].duplicated().any():
        raise ValueError("Audited features and labels must have unique sample IDs.")
    for target in target_columns:
        if target not in labels:
            raise ValueError(f"Audited labels do not contain requested target {target!r}.")
        numeric = pd.to_numeric(labels[target], errors="coerce")
        invalid = labels[target].notna() & (numeric.isna() | ~numeric.isin([0, 1]))
        if invalid.any():
            raise ValueError(f"Target {target!r} must contain only binary values 0, 1, or missing.")
        labels[target] = numeric.astype("Int64")
    if "fold_id" not in splits:
        splits["fold_id"] = "fold_0"
    if splits["sample_id"].isna().any() or splits[["sample_id", "fold_id", "partition"]].duplicated().any():
        raise ValueError("Audited split rows contain missing IDs or duplicate fold/partition keys.")
    if splits["partition"].isna().any() or not set(splits["partition"].astype(str)).issubset({"train", "validation", "test"}):
        raise ValueError("Audited splits contain invalid partition labels.")
    if splits.groupby(["fold_id", "sample_id"])["partition"].nunique().gt(1).any():
        raise ValueError("Audited split sample appears in multiple partitions within a fold.")
    feature_ids = set(features["sample_id"].tolist())
    label_ids = set(labels["sample_id"].tolist())
    if set(splits["sample_id"].tolist()) - feature_ids or set(splits["sample_id"].tolist()) - label_ids:
        raise ValueError("Audited split has sample IDs absent from features or labels.")
    feature_columns = [column for column in features.columns if column != "sample_id"]
    if not feature_columns:
        raise ValueError("Audited feature artifact contains no selected feature columns.")
    return features, labels, splits, {
        "audit_manifest_path": str(manifest_path.resolve()),
        "audit_manifest_sha256": sha256_file(manifest_path),
        "feature_columns": feature_columns,
        "feature_columns_hash": hashlib.sha256(json.dumps(feature_columns, separators=(",", ":")).encode()).hexdigest(),
        "audit_run_id": manifest.get("run_id"),
        "upstream_lineage": manifest.get("upstream_lineage", {}),
        "source_artifacts": manifest.get("source_artifacts", {}),
        "selected_groups": manifest.get("selection", {}).get("selected_groups", []),
        "training_label_policy": manifest.get("training_label_policy", "complete_case"),
    }
