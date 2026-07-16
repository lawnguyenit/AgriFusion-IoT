from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import ROW_INDEX_COLUMNS, SHARED_METADATA_COLUMNS, TAXONOMY_VERSION
from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.validators import dataframe_schema_hash, file_sha256
from Backend.Benchmark.dataset_views.writers import write_csv_file, write_json_file, write_parquet_file


def build_row_index_frame(canonical_df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in ROW_INDEX_COLUMNS if column not in canonical_df.columns]
    if missing:
        raise ValueError("Canonical history is missing required row-index columns: " + ", ".join(missing))
    row_index_df = canonical_df.loc[:, list(ROW_INDEX_COLUMNS)].copy()
    row_index_df.insert(len(ROW_INDEX_COLUMNS), "source_row_position", range(len(row_index_df)))
    return row_index_df


def build_metadata_frame(canonical_df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in SHARED_METADATA_COLUMNS if column not in canonical_df.columns]
    if missing:
        raise ValueError("Canonical history is missing required shared metadata columns: " + ", ".join(missing))
    return canonical_df.loc[:, list(SHARED_METADATA_COLUMNS)].copy()


def build_run_id() -> str:
    return "dataset_views_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_source_manifest_payload(
    *,
    run_id: str,
    config: MaterializationConfig,
    label_status: str,
    selected_public_view_ids: tuple[str, ...],
    materialized_nonpublic_drafts: tuple[str, ...],
    canonical_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    row_index_df: pd.DataFrame,
    audited_run_dir: Path | None,
    taxonomy_audit_path: Path | None,
    layer1_manifest: dict[str, object] | None,
    segment_manifest_path: Path | None,
    segment_manifest_payload: dict[str, object] | None,
    dependency_registry_path: Path,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "pipeline": "dataset_views",
        "created_at_utc": utc_now_iso(),
        "mode": config.mode,
        "label_status": label_status,
        "selected_views": list(selected_public_view_ids),
        "materialized_public_views": list(selected_public_view_ids),
        "materialized_nonpublic_drafts": list(materialized_nonpublic_drafts),
        "row_count": int(len(canonical_df)),
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_audit_path": str(taxonomy_audit_path.resolve()) if taxonomy_audit_path is not None else None,
        "audited_legacy_run_path": str(audited_run_dir.resolve()) if audited_run_dir is not None else None,
        "source": {
            "canonical_history_path": str(config.canonical_history_path.resolve()),
            "feature_catalog_path": str(config.feature_catalog_path.resolve()),
            "layer1_manifest_path": str(config.manifest_path.resolve()) if config.manifest_path is not None else None,
            "segment_manifest_path": str(segment_manifest_path.resolve()) if segment_manifest_path is not None else None,
            "canonical_history_hash": file_sha256(config.canonical_history_path),
            "source_schema_hash": dataframe_schema_hash(canonical_df),
            "feature_catalog_hash": file_sha256(config.feature_catalog_path),
            "dependency_registry_hash": file_sha256(dependency_registry_path),
            "segment_manifest_hash": file_sha256(segment_manifest_path) if segment_manifest_path is not None else None,
        },
        "metadata_columns": list(metadata_df.columns),
        "row_index_columns": list(row_index_df.columns),
        "layer1_manifest": layer1_manifest,
        "segment_manifest": segment_manifest_payload,
    }


def write_shared_outputs(
    *,
    row_index_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    labels_df: pd.DataFrame | None,
    shared_dir: Path,
    parquet_engine: str,
    source_manifest_payload: dict[str, object],
) -> None:
    write_parquet_file(row_index_df, shared_dir / "row_index.parquet", engine=parquet_engine)
    write_csv_file(row_index_df, shared_dir / "row_index.csv")
    write_parquet_file(metadata_df, shared_dir / "metadata.parquet", engine=parquet_engine)
    write_csv_file(metadata_df, shared_dir / "metadata.csv")
    if labels_df is not None:
        write_parquet_file(labels_df, shared_dir / "labels.parquet", engine=parquet_engine)
        write_csv_file(labels_df, shared_dir / "labels.csv")
    write_json_file(shared_dir / "source_manifest.json", source_manifest_payload)
