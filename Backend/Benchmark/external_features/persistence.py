from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators import dataframe_schema_hash, hash_dataframe_rows, stable_hash_object


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_run_id(dataset_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"external_features_{dataset_id}_{stamp}"


def write_feature_artifacts(
    *,
    output_dir: Path,
    feature_frame: pd.DataFrame,
    group_columns: dict[str, list[str]],
    quality: pd.DataFrame,
    manifest: dict[str, object],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=False)
    matrix_path = output_dir / "feature_superset.parquet"
    registry_path = output_dir / "feature_group_registry.json"
    quality_path = output_dir / "window_quality.csv"
    feature_frame.to_parquet(matrix_path, index=False)
    quality.to_csv(quality_path, index=False)
    group_registry = {
        name: {
            "columns": columns,
            "columns_hash": stable_hash_object(columns),
            "values_hash": _hash_frame(feature_frame.loc[:, columns]),
        }
        for name, columns in group_columns.items()
    }
    registry = {
        "schema_version": 1,
        "artifact_name": "external_feature_superset",
        "matrix_path": str(matrix_path.resolve()),
        "matrix_sha256": sha256_file(matrix_path),
        "matrix_schema_hash": dataframe_schema_hash(feature_frame),
        "feature_rows_hash": hash_dataframe_rows(feature_frame.loc[:, registry_columns(feature_frame)]),
        "ordered_sample_id_hash": stable_hash_object(feature_frame["sample_id"].astype("string").tolist()),
        "source_row_position_hash": stable_hash_object(feature_frame["source_row_position"].tolist()),
        "row_count": int(len(feature_frame)),
        "identifier_columns": ["sample_id", "source_row_position"],
        "ordered_feature_columns": [column for column in feature_frame.columns if column not in {"sample_id", "source_row_position"}],
        "feature_groups": group_registry,
        **{
            key: manifest[key]
            for key in (
                "dataset_id", "intake_manifest_path", "intake_manifest_sha256",
                "canonical_path", "canonical_sha256", "raw_manifest_path", "raw_manifest_sha256",
                "dataset_metadata",
            )
            if key in manifest
        },
    }
    registry["ordered_feature_columns_hash"] = stable_hash_object(registry["ordered_feature_columns"])
    manifest.update(
        {
            "feature_matrix_path": str(matrix_path.resolve()),
            "feature_matrix_sha256": registry["matrix_sha256"],
            "feature_registry_path": str(registry_path.resolve()),
            "feature_registry_sha256": None,
            "window_quality_path": str(quality_path.resolve()),
            "row_count": int(len(feature_frame)),
            "feature_count": len(registry["ordered_feature_columns"]),
            "feature_groups": group_registry,
        }
    )
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["feature_registry_sha256"] = sha256_file(registry_path)
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        f"# External feature processing: {manifest['dataset_id']}",
        "",
        f"- Run: `{manifest['run_id']}`",
        f"- Canonical source hash: `{manifest['canonical_sha256']}`",
        f"- Samples: {len(feature_frame)}",
        f"- Model feature columns: {len(registry['ordered_feature_columns'])}",
        f"- Feature groups: `{', '.join(group_registry)}`",
        "",
        "Only fields registered as measurements by the source adapter enter the feature matrix. "
        "Criterion-only and post-hoc operational evidence remain outside X.",
        "",
    ]
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    catalog = []
    for path in (matrix_path, registry_path, quality_path, output_dir / "run_manifest.json", output_dir / "report.md"):
        catalog.append({"path": path.name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    (output_dir / "artifact_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return matrix_path, registry_path


def _hash_frame(frame: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=False).values.tobytes()).hexdigest()


def registry_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column not in {"sample_id", "source_row_position"}]
