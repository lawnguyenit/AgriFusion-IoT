from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import (
    BENCHMARK_READY_MODE,
    bundled_dependency_registry_path,
    get_taxonomy_entry,
    get_view_definition,
    load_dependency_registry,
)
from Backend.Benchmark.dataset_views.contracts import MaterializationConfig, MaterializationResult
from Backend.Benchmark.dataset_views.loaders import (
    load_canonical_history,
    load_feature_catalog,
    load_label_artifact,
    load_layer1_manifest,
    load_segment_manifest,
)
from Backend.Benchmark.dataset_views.pipelines.shared_outputs import (
    build_metadata_frame,
    build_row_index_frame,
    build_run_id,
    build_source_manifest_payload,
    write_artifact_guides,
    write_shared_outputs,
)
from Backend.Benchmark.dataset_views.pipelines.standard_views import materialize_standard_view
from Backend.Benchmark.dataset_views.pipelines.runtime import (
    requires_segment_manifest,
    resolve_selected_public_view_ids,
    validate_requested_views,
)
from Backend.Benchmark.dataset_views.reports import build_current_scope_taxonomy_report_payload
from Backend.Benchmark.dataset_views.reports.lineage_contracts import emit_tranche0_lineage_artifacts
from Backend.Benchmark.dataset_views.selectors import normalize_feature_catalog
from Backend.Benchmark.dataset_views.validators import ensure_parquet_engine, validate_label_join, validate_unique_record_ids
from Backend.Benchmark.dataset_views.writers import write_json_file


def materialize_dataset_views(config: MaterializationConfig) -> MaterializationResult:
    selected_public_view_ids = resolve_selected_public_view_ids(config)
    validate_requested_views(selected_public_view_ids=selected_public_view_ids, config=config)

    parquet_engine = ensure_parquet_engine()
    canonical_df = load_canonical_history(config.canonical_history_path)
    feature_catalog_df = load_feature_catalog(config.feature_catalog_path)
    layer1_manifest = load_layer1_manifest(config.manifest_path)
    segment_manifest_path: Path | None = None
    segment_manifest_payload: dict[str, object] | None = None
    if requires_segment_manifest(selected_public_view_ids):
        segment_manifest_path, segment_manifest_payload = load_segment_manifest(config.manifest_path)
    catalog_index = normalize_feature_catalog(feature_catalog_df)
    dependency_registry = load_dependency_registry()
    dependency_registry_path = bundled_dependency_registry_path()

    validate_unique_record_ids(canonical_df, key_column="record.id")

    run_id = build_run_id()
    output_dir = config.output_root.resolve() / run_id
    shared_dir = output_dir / "shared"
    views_dir = output_dir / "views"
    reports_dir = output_dir / "reports"
    shared_dir.mkdir(parents=True, exist_ok=False)
    views_dir.mkdir(parents=True, exist_ok=False)
    reports_dir.mkdir(parents=True, exist_ok=False)

    current_scope_report_path = reports_dir / "current_scope_taxonomy_report.json"
    write_json_file(
        current_scope_report_path,
        build_current_scope_taxonomy_report_payload(selected_public_view_ids),
    )

    row_index_df = build_row_index_frame(canonical_df)
    metadata_df = build_metadata_frame(canonical_df)

    label_status = "not_attached"
    labels_df: pd.DataFrame | None = None
    label_columns: list[str] = []
    if config.mode == BENCHMARK_READY_MODE:
        if config.label_config is None:
            raise ValueError("benchmark-ready mode requires an explicit label artifact keyed by 'record.id'.")
        labels_df = load_label_artifact(config.label_config)
        labels_df = validate_label_join(row_index_df=row_index_df, labels_df=labels_df, key_column=config.label_config.key_column)
        label_columns = [column for column in labels_df.columns if column != config.label_config.key_column]
        label_status = "attached"
    elif config.label_config is not None:
        raise ValueError("feature-only mode does not accept a label artifact. Use benchmark-ready mode instead.")

    source_manifest_payload = build_source_manifest_payload(
        run_id=run_id,
        config=config,
        label_status=label_status,
        selected_public_view_ids=selected_public_view_ids,
        canonical_df=canonical_df,
        metadata_df=metadata_df,
        row_index_df=row_index_df,
        audited_run_dir=None,
        current_scope_report_path=current_scope_report_path,
        legacy_taxonomy_audit_path=None,
        layer1_manifest=layer1_manifest,
        segment_manifest_path=segment_manifest_path,
        segment_manifest_payload=segment_manifest_payload,
        dependency_registry_path=dependency_registry_path,
    )

    write_shared_outputs(
        row_index_df=row_index_df,
        metadata_df=metadata_df,
        labels_df=labels_df,
        shared_dir=shared_dir,
        parquet_engine=parquet_engine,
        source_manifest_payload=source_manifest_payload,
    )

    canonical_columns = tuple(canonical_df.columns)
    for view_id in selected_public_view_ids:
        taxonomy_entry = get_taxonomy_entry(view_id)
        view_definition = get_view_definition(view_id)
        materialize_standard_view(
            taxonomy_entry=taxonomy_entry,
            view_definition=view_definition,
            canonical_df=canonical_df,
            canonical_columns=canonical_columns,
            catalog_index=catalog_index,
            dependency_registry=dependency_registry,
            label_columns=label_columns,
            metadata_columns=list(metadata_df.columns),
            output_dir=views_dir / view_id,
            parquet_engine=parquet_engine,
            source_manifest_payload=source_manifest_payload,
            segment_manifest_payload=segment_manifest_payload,
        )

    emit_tranche0_lineage_artifacts(
        output_dir=output_dir,
        shared_dir=shared_dir,
        canonical_columns=canonical_columns,
        row_index_df=row_index_df,
        catalog_index=catalog_index,
        dependency_registry=dependency_registry,
        parquet_engine=parquet_engine,
    )
    write_artifact_guides(
        output_dir=output_dir,
        shared_dir=shared_dir,
        selected_public_view_ids=selected_public_view_ids,
        current_scope_report_path=current_scope_report_path,
        legacy_taxonomy_audit_path=None,
    )

    return MaterializationResult(
        run_id=run_id,
        output_dir=output_dir,
        label_status=label_status,
        selected_views=selected_public_view_ids,
        row_count=int(len(canonical_df)),
        materialized_nonpublic_drafts=(),
    )
