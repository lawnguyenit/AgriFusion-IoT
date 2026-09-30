from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators import (
    dataframe_schema_hash,
    file_sha256,
    hash_dataframe_rows,
    stable_hash_object,
)
from Backend.Benchmark.dataset_views.writers import write_json_file, write_parquet_file


def materialize_superset_feature_artifact(
    *,
    views_dir: Path,
    shared_dir: Path,
    selected_view_ids: tuple[str, ...],
    row_index: pd.DataFrame,
    parquet_engine: str,
) -> dict[str, object]:
    row_contract = json.loads((shared_dir / "row_index_contract.json").read_text(encoding="utf-8"))
    feature_frame, source_manifests = _merge_selected_view_matrices(
        views_dir=views_dir,
        selected_view_ids=selected_view_ids,
        row_index=row_index,
        row_contract=row_contract,
    )
    group_registry = _build_feature_group_registry(feature_frame)
    master = row_index.loc[:, ["record.id", "source_row_position"]].copy()
    master = master.rename(columns={"record.id": "sample_id"})
    master["sample_id"] = master["sample_id"].astype("string")
    master = pd.concat([master.reset_index(drop=True), feature_frame.reset_index(drop=True)], axis=1)

    matrix_path = shared_dir / "feature_superset.parquet"
    registry_path = shared_dir / "feature_group_registry.json"
    write_parquet_file(master, matrix_path, engine=parquet_engine)
    registry = {
        "schema_version": 1,
        "artifact_name": "feature_superset",
        "matrix_path": str(matrix_path.resolve()),
        "matrix_sha256": file_sha256(matrix_path),
        "matrix_schema_hash": dataframe_schema_hash(master),
        "row_count": int(len(master)),
        "row_index_hash": row_contract["row_index_hash"],
        "record_id_hash": row_contract["record_id_hash"],
        "identifier_columns": ["sample_id", "source_row_position"],
        "selected_source_views": list(selected_view_ids),
        "source_view_manifests": source_manifests,
        "ordered_feature_columns": list(feature_frame.columns),
        "ordered_feature_columns_hash": stable_hash_object(list(feature_frame.columns)),
        "feature_rows_hash": hash_dataframe_rows(feature_frame),
        "feature_groups": group_registry,
    }
    write_json_file(registry_path, registry)
    return {
        "matrix_path": str(matrix_path.resolve()),
        "matrix_sha256": registry["matrix_sha256"],
        "registry_path": str(registry_path.resolve()),
        "row_count": int(len(master)),
        "feature_count": int(len(feature_frame.columns)),
        "ordered_feature_columns_hash": registry["ordered_feature_columns_hash"],
        "feature_groups": group_registry,
    }


def _merge_selected_view_matrices(
    *,
    views_dir: Path,
    selected_view_ids: tuple[str, ...],
    row_index: pd.DataFrame,
    row_contract: dict[str, object],
) -> tuple[pd.DataFrame, dict[str, dict[str, str]]]:
    merged = pd.DataFrame(index=range(len(row_index)))
    sources: dict[str, dict[str, str]] = {}
    for view_id in selected_view_ids:
        view_dir = views_dir / view_id
        manifest = json.loads((view_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("sample_id_hash") != row_contract.get("record_id_hash"):
            raise ValueError(f"View {view_id!r} sample identity does not match shared row_index.")
        if manifest.get("row_index_hash") != row_contract.get("file_hash"):
            raise ValueError(f"View {view_id!r} row order does not match shared row_index.")
        feature_list = json.loads((view_dir / "feature_columns.json").read_text(encoding="utf-8"))
        expected_columns = list(feature_list["allowed_feature_columns"])
        matrix_path = view_dir / "X.parquet"
        frame = pd.read_parquet(matrix_path)
        if len(frame) != len(row_index):
            raise ValueError(f"View {view_id!r} row count does not match shared row_index.")
        if list(frame.columns) != expected_columns:
            raise ValueError(f"View {view_id!r} matrix columns do not match its ordered feature contract.")
        if file_sha256(matrix_path) != manifest.get("feature_artifact_hash"):
            raise ValueError(f"View {view_id!r} matrix checksum does not match its manifest.")
        schema_payload = json.loads((view_dir / "schema.json").read_text(encoding="utf-8"))
        if schema_payload.get("schema_hash") != manifest.get("feature_schema_hash"):
            raise ValueError(f"View {view_id!r} schema checksum does not match its manifest.")
        if dataframe_schema_hash(frame) != manifest.get("feature_schema_hash"):
            raise ValueError(f"View {view_id!r} matrix schema does not match its manifest.")
        for column in frame.columns:
            if column in merged.columns:
                if not _feature_values_match(merged[column], frame[column]):
                    raise ValueError(f"Overlapping feature {column!r} differs across selected source views.")
            else:
                merged[column] = frame[column].reset_index(drop=True)
        sources[view_id] = {
            "matrix_path": str(matrix_path.resolve()),
            "matrix_sha256": file_sha256(matrix_path),
            "schema_hash": str(manifest.get("feature_schema_hash", "")),
            "row_count": int(len(frame)),
            "ordered_feature_columns_hash": str(manifest.get("ordered_feature_list_hash", "")),
        }
    if merged.empty and len(row_index):
        raise ValueError("Selected views produced an empty superset feature matrix.")
    return merged, sources


def _feature_values_match(left: pd.Series, right: pd.Series) -> bool:
    """Compare overlapping feature values without treating dtype as semantics."""
    left = left.reset_index(drop=True)
    right = right.reset_index(drop=True)
    if len(left) != len(right):
        return False
    try:
        pd.testing.assert_series_equal(
            left,
            right,
            check_dtype=False,
            check_names=False,
            check_exact=True,
        )
    except AssertionError:
        return False
    return True


def _build_feature_group_registry(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    groups: dict[str, list[str]] = {"values": [], "window_3h": [], "window_8h": []}
    for column in frame.columns:
        name = str(column)
        if "__3h_" in name:
            groups["window_3h"].append(name)
        elif "__8h_" in name:
            groups["window_8h"].append(name)
        else:
            groups["values"].append(name)
    return {
        group: {
            "columns": features,
            "columns_hash": stable_hash_object(features),
            "values_hash": hash_dataframe_rows(frame.loc[:, features]),
        }
        for group, features in groups.items()
        if features
    }
