from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import get_view_definition
from Backend.Benchmark.dataset_views.contracts import TaxonomyEntry, ViewDefinition
from Backend.Benchmark.dataset_views.reports import build_quality_report
from Backend.Benchmark.dataset_views.selectors import select_view_features
from Backend.Benchmark.dataset_views.validators import (
    hash_dataframe_rows,
    stable_hash_object,
    validate_metadata_separation,
    validate_row_alignment,
    validate_selection_result,
)
from Backend.Benchmark.dataset_views.windowing.masking import coerce_boolean_series, resolve_validity_column
from Backend.Benchmark.dataset_views.writers import write_csv_file, write_json_file, write_parquet_file


def materialize_explicit_view(
    *,
    taxonomy_entry: TaxonomyEntry,
    view_definition: ViewDefinition,
    canonical_df: pd.DataFrame,
    canonical_columns: tuple[str, ...],
    catalog_index: dict[str, object],
    dependency_registry: dict[str, object],
    label_columns: list[str],
    metadata_columns: list[str],
    output_dir: Path,
    parquet_engine: str,
    source_manifest_payload: dict[str, object],
) -> None:
    selection = select_view_features(
        view_definition=view_definition,
        canonical_columns=canonical_columns,
        catalog_index=catalog_index,
        dependency_registry=dependency_registry,
    )
    validate_selection_result(selection)

    feature_columns = list(selection.ordered_features)
    validate_metadata_separation(metadata_columns=metadata_columns, feature_columns=feature_columns, label_columns=label_columns)

    feature_frame = build_explicit_feature_frame(
        canonical_df=canonical_df,
        feature_columns=feature_columns,
    )
    validate_row_alignment(
        reference_length=len(canonical_df),
        candidate_length=len(feature_frame),
        artifact_name=f"{view_definition.view_id}/X.parquet",
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    write_parquet_file(feature_frame, output_dir / "X.parquet", engine=parquet_engine)
    write_csv_file(feature_frame, output_dir / "X.csv")

    data_hash = hash_dataframe_rows(feature_frame)
    schema_payload = {
        "view_id": view_definition.view_id,
        "row_count": int(len(feature_frame)),
        "feature_count": int(feature_frame.shape[1]),
        "columns": [{"name": column, "dtype": str(dtype)} for column, dtype in feature_frame.dtypes.items()],
    }
    quality_report = build_quality_report(
        view_id=view_definition.view_id,
        feature_frame=feature_frame,
        selection=selection,
        catalog_index=catalog_index,
    )
    manifest_payload = {
        "view_id": view_definition.view_id,
        "numeric_alias": taxonomy_entry.numeric_alias,
        "status": taxonomy_entry.status,
        "batch": taxonomy_entry.batch,
        "grain": taxonomy_entry.grain,
        "description": view_definition.description,
        "selection_mode": view_definition.selection_mode,
        "created_at_utc": _utc_now_iso(),
        "label_status": source_manifest_payload["label_status"],
        "row_count": int(len(feature_frame)),
        "ordered_feature_list": feature_columns,
        "ordered_feature_list_hash": stable_hash_object(feature_columns),
        "x_data_hash": data_hash,
        "metadata_columns": metadata_columns,
        "debug_csv_paths": {
            "feature_matrix_csv": str((output_dir / "X.csv").resolve()),
        },
        "source_canonical_hash": source_manifest_payload["source"]["canonical_history_hash"],
        "source_schema_hash": source_manifest_payload["source"]["source_schema_hash"],
        "feature_catalog_hash": source_manifest_payload["source"]["feature_catalog_hash"],
        "view_configuration_hash": stable_hash_object(asdict(view_definition)),
        "dependency_registry_hash": source_manifest_payload["source"]["dependency_registry_hash"],
        "proxy_counts": selection.dependency_type_counts,
        "selection_diagnostics": {
            "missing_from_canonical": list(selection.missing_from_canonical),
            "missing_from_catalog": list(selection.missing_from_catalog),
            "excluded_by_blacklist": list(selection.excluded_by_blacklist),
            "excluded_by_governance": list(selection.excluded_by_governance),
            "excluded_by_registry": list(selection.excluded_by_registry),
            "unresolved_risks": list(selection.unresolved_risks),
        },
    }
    if taxonomy_entry.semantic_view_id == "v5_proxy_reduced_draft":
        v0_definition = get_view_definition("v0_minimal_sensor")
        v0_frame = build_explicit_feature_frame(
            canonical_df=canonical_df,
            feature_columns=list(v0_definition.explicit_features),
        )
        manifest_payload["invalid_independent_view_reason"] = {
            "ordered_feature_equality_with_v0": bool(feature_columns == list(v0_definition.explicit_features)),
            "x_hash_equality_with_v0": bool(data_hash == hash_dataframe_rows(v0_frame)),
            "candidate_universe_status": "incorrectly_defined",
            "summary": (
                "This proxy-reduced draft is not an independent benchmark view. "
                "Its current candidate universe definition collapses it onto the v0 feature set."
            ),
        }

    write_json_file(output_dir / "manifest.json", manifest_payload)
    write_json_file(output_dir / "schema.json", schema_payload)
    write_json_file(output_dir / "quality_report.json", quality_report)


def build_explicit_feature_frame(
    *,
    canonical_df: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:
    feature_frame = canonical_df.loc[:, feature_columns].copy()
    for feature_column in feature_columns:
        validity_column = resolve_validity_column(feature_column)
        if validity_column is None or validity_column not in canonical_df.columns:
            continue
        numeric = pd.to_numeric(canonical_df[feature_column], errors="coerce")
        valid_mask = coerce_boolean_series(canonical_df[validity_column])
        feature_frame[feature_column] = numeric.where(valid_mask, pd.NA).astype("Float64")
    return feature_frame


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
