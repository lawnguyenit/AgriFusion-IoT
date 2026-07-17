from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.contracts.artifact_contracts import (
    build_feature_columns_payload,
    build_schema_payload,
)
from Backend.Benchmark.dataset_views.contracts import TaxonomyEntry, ViewDefinition, ViewSelectionResult
from Backend.Benchmark.dataset_views.row_views import materialize_explicit_view
from Backend.Benchmark.dataset_views.reports import build_quality_report
from Backend.Benchmark.dataset_views.validators import (
    file_sha256,
    hash_dataframe_rows,
    stable_hash_object,
    validate_metadata_separation,
    validate_row_alignment,
)
from Backend.Benchmark.dataset_views.windowing import build_v2_sensor_window_view
from Backend.Benchmark.dataset_views.writers import write_csv_file, write_json_file, write_parquet_file

from .shared_outputs import utc_now_iso


def materialize_standard_view(
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
    segment_manifest_payload: dict[str, object] | None,
) -> None:
    if view_definition.selection_mode == "window_engineered":
        materialize_window_view(
            taxonomy_entry=taxonomy_entry,
            view_definition=view_definition,
            canonical_df=canonical_df,
            catalog_index=catalog_index,
            metadata_columns=metadata_columns,
            output_dir=output_dir,
            parquet_engine=parquet_engine,
            source_manifest_payload=source_manifest_payload,
            segment_manifest_payload=segment_manifest_payload,
        )
        return

    materialize_explicit_view(
        taxonomy_entry=taxonomy_entry,
        view_definition=view_definition,
        canonical_df=canonical_df,
        canonical_columns=canonical_columns,
        catalog_index=catalog_index,
        dependency_registry=dependency_registry,
        label_columns=label_columns,
        metadata_columns=metadata_columns,
        output_dir=output_dir,
        parquet_engine=parquet_engine,
        source_manifest_payload=source_manifest_payload,
    )


def materialize_window_view(
    *,
    taxonomy_entry: TaxonomyEntry,
    view_definition: ViewDefinition,
    canonical_df: pd.DataFrame,
    catalog_index: dict[str, object],
    metadata_columns: list[str],
    output_dir: Path,
    parquet_engine: str,
    source_manifest_payload: dict[str, object],
    segment_manifest_payload: dict[str, object] | None,
) -> None:
    if segment_manifest_payload is None:
        raise ValueError("v2_sensor_window requires the Layer1 segment manifest, but it was not loaded.")

    artifacts = build_v2_sensor_window_view(
        canonical_df=canonical_df,
        measurement_columns=view_definition.explicit_features,
        segment_manifest=segment_manifest_payload,
        selected_horizon_names=view_definition.window_horizon_names,
    )
    validate_metadata_separation(
        metadata_columns=metadata_columns,
        feature_columns=list(artifacts.feature_frame.columns),
        label_columns=[],
    )
    validate_row_alignment(
        reference_length=len(canonical_df),
        candidate_length=len(artifacts.feature_frame),
        artifact_name=f"{view_definition.view_id}/X.parquet",
    )
    validate_row_alignment(
        reference_length=len(canonical_df),
        candidate_length=len(artifacts.audit_frame),
        artifact_name=f"{view_definition.view_id}/window_quality_audit.parquet",
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    x_parquet_path = output_dir / "X.parquet"
    x_csv_path = output_dir / "X.csv"
    audit_parquet_path = output_dir / "window_quality_audit.parquet"
    audit_csv_path = output_dir / "window_quality_audit.csv"
    schema_path = output_dir / "schema.json"
    quality_report_path = output_dir / "quality_report.json"
    feature_columns_path = output_dir / "feature_columns.json"
    row_index_path = Path(str(source_manifest_payload["shared_artifacts"]["row_index"]["parquet_path"]))
    write_parquet_file(artifacts.feature_frame, x_parquet_path, engine=parquet_engine)
    write_csv_file(artifacts.feature_frame, x_csv_path)
    write_parquet_file(artifacts.audit_frame, audit_parquet_path, engine=parquet_engine)
    write_csv_file(artifacts.audit_frame, audit_csv_path)

    feature_names = list(artifacts.feature_frame.columns)
    selection = ViewSelectionResult(
        view_definition=view_definition,
        ordered_features=tuple(feature_names),
    )
    data_hash = hash_dataframe_rows(artifacts.feature_frame)
    schema_payload = build_schema_payload(view_id=view_definition.view_id, feature_frame=artifacts.feature_frame)
    quality_report = build_quality_report(
        view_id=view_definition.view_id,
        feature_frame=artifacts.feature_frame,
        selection=selection,
        catalog_index=catalog_index,
        feature_metadata=artifacts.feature_metadata,
        extra_sections=artifacts.quality_sections,
    )
    feature_columns_payload = build_feature_columns_payload(
        view_id=view_definition.view_id,
        ordered_feature_list=feature_names,
        metadata_columns=metadata_columns,
        audit_only_columns=list(artifacts.audit_frame.columns),
        identifier_source_path=row_index_path,
        source_manifest_payload=source_manifest_payload,
    )
    write_json_file(schema_path, schema_payload)
    write_json_file(quality_report_path, quality_report)
    write_json_file(feature_columns_path, feature_columns_payload)
    manifest_payload = {
        "view_id": view_definition.view_id,
        "numeric_alias": taxonomy_entry.numeric_alias,
        "status": taxonomy_entry.status,
        "batch": taxonomy_entry.batch,
        "grain": taxonomy_entry.grain,
        "description": view_definition.description,
        "selection_mode": view_definition.selection_mode,
        "created_at_utc": utc_now_iso(),
        "label_status": source_manifest_payload["label_status"],
        "row_count": int(len(artifacts.feature_frame)),
        "ordered_feature_list": feature_names,
        "ordered_feature_list_hash": stable_hash_object(feature_names),
        "x_data_hash": data_hash,
        "feature_artifact_path": str(x_parquet_path.resolve()),
        "feature_artifact_hash": file_sha256(x_parquet_path),
        "feature_schema_path": str(schema_path.resolve()),
        "feature_schema_hash": str(schema_payload["schema_hash"]),
        "feature_columns_path": str(feature_columns_path.resolve()),
        "feature_columns_hash": file_sha256(feature_columns_path),
        "feature_generator_config_hash": stable_hash_object(
            {
                "view_id": view_definition.view_id,
                "selection_mode": view_definition.selection_mode,
                "explicit_features": list(view_definition.explicit_features),
                "window_horizon_names": list(view_definition.window_horizon_names),
            }
        ),
        "feature_generator_code_commit": str(source_manifest_payload["source"]["pipeline_code_commit"]),
        "materialization_config_hash": str(source_manifest_payload["source"]["materialization_config_hash"]),
        "row_index_path": str(row_index_path.resolve()),
        "row_index_hash": str(source_manifest_payload["shared_artifacts"]["row_index"]["file_hash"]),
        "sample_id_hash": str(source_manifest_payload["shared_artifacts"]["row_index"]["record_id_hash"]),
        "identifier_columns": feature_columns_payload["identifier_columns"],
        "metadata_columns": metadata_columns,
        "debug_csv_paths": {
            "feature_matrix_csv": str(x_csv_path.resolve()),
            "window_quality_audit_csv": str(audit_csv_path.resolve()),
        },
        "source_canonical_hash": source_manifest_payload["source"]["canonical_history_hash"],
        "source_schema_hash": source_manifest_payload["source"]["source_schema_hash"],
        "feature_catalog_hash": source_manifest_payload["source"]["feature_catalog_hash"],
        "view_configuration_hash": stable_hash_object(
            {
                "view_id": view_definition.view_id,
                "selection_mode": view_definition.selection_mode,
                "explicit_features": list(view_definition.explicit_features),
                "window_horizon_names": list(view_definition.window_horizon_names),
            }
        ),
        "dependency_registry_hash": source_manifest_payload["source"]["dependency_registry_hash"],
        "proxy_counts": {},
        "selection_diagnostics": {
            "missing_from_canonical": [],
            "missing_from_catalog": [],
            "excluded_by_blacklist": [],
            "excluded_by_governance": [],
            "excluded_by_registry": [],
            "unresolved_risks": [],
        },
    }
    manifest_payload.update(artifacts.manifest_sections)
    write_json_file(output_dir / "manifest.json", manifest_payload)
