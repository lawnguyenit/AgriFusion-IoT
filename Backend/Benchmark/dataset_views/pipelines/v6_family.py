from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import (
    TAXONOMY_VERSION,
    V6_AUXILIARY_FEATURE_COLUMNS,
    V6_DATASET_VERSION,
    V6_OUTPUT_DIRNAME,
    V6_PRIMARY_FEATURE_COLUMNS,
)
from Backend.Benchmark.dataset_views.contracts import TaxonomyEntry, ViewDefinition
from Backend.Benchmark.dataset_views.validators import (
    hash_dataframe_rows,
    stable_hash_object,
    validate_no_infinite_values,
    validate_row_alignment,
)
from Backend.Benchmark.dataset_views.v6_environment import (
    V6Artifacts,
    apply_environment_targets,
    build_chunked_sequence_dataset,
    build_v6_audit_payloads,
    build_v6_distribution_frames,
    build_view_frames,
    prepare_environment_records,
    resample_continuity_segments,
)
from Backend.Benchmark.dataset_views.writers import write_csv_file, write_json_file, write_parquet_file

from .shared_outputs import utc_now_iso


def prepare_v6_family_context(
    *,
    canonical_df: pd.DataFrame,
    segment_manifest_payload: dict[str, object],
    output_dir: Path,
    parquet_engine: str,
    source_manifest_payload: dict[str, object],
) -> dict[str, object]:
    prepared_df, cadence_by_segment = prepare_environment_records(
        canonical_df,
        segment_manifest=segment_manifest_payload,
    )
    resampled_df = resample_continuity_segments(prepared_df, cadence_by_segment=cadence_by_segment)
    targeted_df, threshold_manifest_payload = apply_environment_targets(resampled_df)
    sequence_rows_df, chunk_manifest_df, discarded_chunks_df, event_fragment_registry_df = build_chunked_sequence_dataset(
        targeted_df,
        cadence_by_segment=cadence_by_segment,
    )
    x_df, y_df, sequence_index_df = build_view_frames(sequence_rows_df)
    (
        original_event_distribution_df,
        day_distribution_df,
        chunk_distribution_df,
        split_group_manifest_df,
        original_event_integrity_payload,
    ) = build_v6_distribution_frames(sequence_rows_df=sequence_rows_df)

    v6_dir = output_dir / V6_OUTPUT_DIRNAME
    v6_dir.mkdir(parents=True, exist_ok=False)
    _write_v6_artifacts(
        v6_dir=v6_dir,
        parquet_engine=parquet_engine,
        sequence_rows_df=sequence_rows_df,
        chunk_manifest_df=chunk_manifest_df,
        discarded_chunks_df=discarded_chunks_df,
        event_fragment_registry_df=event_fragment_registry_df,
        original_event_distribution_df=original_event_distribution_df,
        day_distribution_df=day_distribution_df,
        chunk_distribution_df=chunk_distribution_df,
        split_group_manifest_df=split_group_manifest_df,
        original_event_integrity_payload=original_event_integrity_payload,
        threshold_manifest_payload=threshold_manifest_payload,
        x_df=x_df,
        y_df=y_df,
        sequence_index_df=sequence_index_df,
    )

    validate_no_infinite_values(x_df, artifact_name="V6/X.parquet")
    quality_report_payload, schema_payload, audit_markdown = build_v6_audit_payloads(
        sequence_rows_df=sequence_rows_df,
        chunk_manifest_df=chunk_manifest_df,
        discarded_chunks_df=discarded_chunks_df,
        event_fragment_registry_df=event_fragment_registry_df,
        threshold_manifest_payload=threshold_manifest_payload,
        original_event_distribution_df=original_event_distribution_df,
        day_distribution_df=day_distribution_df,
        chunk_distribution_df=chunk_distribution_df,
        split_group_manifest_df=split_group_manifest_df,
        original_event_integrity_payload=original_event_integrity_payload,
    )
    (v6_dir / "V6_audit_report.md").write_text(audit_markdown, encoding="utf-8")

    dataset_manifest_payload = {
        "view_id": "v6_sequence_8h",
        "created_at_utc": utc_now_iso(),
        "dataset_version": V6_DATASET_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "status": "ACTIVE_ENVIRONMENTAL_SEQUENCE",
        "source_canonical_hash": source_manifest_payload["source"]["canonical_history_hash"],
        "source_schema_hash": source_manifest_payload["source"]["source_schema_hash"],
        "feature_catalog_hash": source_manifest_payload["source"]["feature_catalog_hash"],
        "sequence_rows_hash": hash_dataframe_rows(sequence_rows_df) if not sequence_rows_df.empty else stable_hash_object([]),
        "x_hash": hash_dataframe_rows(x_df) if not x_df.empty else stable_hash_object([]),
        "y_hash": hash_dataframe_rows(y_df) if not y_df.empty else stable_hash_object([]),
        "default_feature_columns": list(V6_PRIMARY_FEATURE_COLUMNS),
        "auxiliary_feature_columns": list(V6_AUXILIARY_FEATURE_COLUMNS),
        "output_paths": {
            "sequence_rows_parquet": str((v6_dir / "sequence_rows.parquet").resolve()),
            "sequence_rows_csv": str((v6_dir / "sequence_rows.csv").resolve()),
            "chunk_manifest_csv": str((v6_dir / "chunk_manifest.csv").resolve()),
            "discarded_chunks_csv": str((v6_dir / "discarded_chunks.csv").resolve()),
            "event_fragment_registry_csv": str((v6_dir / "event_fragment_registry.csv").resolve()),
            "original_event_distribution_csv": str((v6_dir / "original_event_distribution.csv").resolve()),
            "day_distribution_csv": str((v6_dir / "day_distribution.csv").resolve()),
            "chunk_distribution_csv": str((v6_dir / "chunk_distribution.csv").resolve()),
            "split_group_manifest_csv": str((v6_dir / "split_group_manifest.csv").resolve()),
            "original_event_integrity_json": str((v6_dir / "original_event_integrity.json").resolve()),
            "threshold_manifest_json": str((v6_dir / "threshold_manifest.json").resolve()),
            "x_parquet": str((v6_dir / "X.parquet").resolve()),
            "y_parquet": str((v6_dir / "y.parquet").resolve()),
            "sequence_index_parquet": str((v6_dir / "sequence_index.parquet").resolve()),
            "audit_report_md": str((v6_dir / "V6_audit_report.md").resolve()),
        },
    }
    write_json_file(v6_dir / "dataset_manifest.json", dataset_manifest_payload)

    return {
        "artifacts": V6Artifacts(
            sequence_rows_df=sequence_rows_df,
            kept_sequence_rows_df=sequence_rows_df.loc[sequence_rows_df["chunk_kept"].fillna(False)].copy(),
            chunk_manifest_df=chunk_manifest_df,
            discarded_chunks_df=discarded_chunks_df,
            event_fragment_registry_df=event_fragment_registry_df,
            original_event_distribution_df=original_event_distribution_df,
            day_distribution_df=day_distribution_df,
            chunk_distribution_df=chunk_distribution_df,
            split_group_manifest_df=split_group_manifest_df,
            threshold_manifest_payload=threshold_manifest_payload,
            original_event_integrity_payload=original_event_integrity_payload,
            dataset_manifest_payload=dataset_manifest_payload,
            schema_payload=schema_payload,
            quality_report_payload=quality_report_payload,
            audit_report_markdown=audit_markdown,
        ),
        "v6_dir": v6_dir,
    }


def materialize_v6_view(
    *,
    taxonomy_entry: TaxonomyEntry,
    view_definition: ViewDefinition,
    v6_context: dict[str, object],
    output_dir: Path,
    parquet_engine: str,
    source_manifest_payload: dict[str, object],
) -> None:
    del parquet_engine
    del source_manifest_payload
    artifacts: V6Artifacts = v6_context["artifacts"]
    kept_rows = artifacts.kept_sequence_rows_df
    validate_row_alignment(
        reference_length=int(len(kept_rows)),
        candidate_length=int(len(kept_rows)),
        artifact_name=f"{view_definition.view_id}/X.parquet",
    )

    output_dir.mkdir(parents=True, exist_ok=False)
    manifest_payload = dict(artifacts.dataset_manifest_payload)
    manifest_payload.update(
        {
            "numeric_alias": taxonomy_entry.numeric_alias,
            "batch": taxonomy_entry.batch,
            "grain": taxonomy_entry.grain,
            "description": view_definition.description,
            "selection_mode": view_definition.selection_mode,
            "view_dir": str(output_dir.resolve()),
            "dataset_manifest_path": str((v6_context["v6_dir"] / "dataset_manifest.json").resolve()),
        }
    )
    write_json_file(output_dir / "manifest.json", manifest_payload)
    write_json_file(output_dir / "schema.json", artifacts.schema_payload)
    write_json_file(output_dir / "quality_report.json", artifacts.quality_report_payload)


def _write_v6_artifacts(
    *,
    v6_dir: Path,
    parquet_engine: str,
    sequence_rows_df: pd.DataFrame,
    chunk_manifest_df: pd.DataFrame,
    discarded_chunks_df: pd.DataFrame,
    event_fragment_registry_df: pd.DataFrame,
    original_event_distribution_df: pd.DataFrame,
    day_distribution_df: pd.DataFrame,
    chunk_distribution_df: pd.DataFrame,
    split_group_manifest_df: pd.DataFrame,
    original_event_integrity_payload: dict[str, object],
    threshold_manifest_payload: dict[str, object],
    x_df: pd.DataFrame,
    y_df: pd.DataFrame,
    sequence_index_df: pd.DataFrame,
) -> None:
    auxiliary_columns = [column for column in V6_AUXILIARY_FEATURE_COLUMNS if column in sequence_index_df.columns]
    auxiliary_df = sequence_index_df.loc[:, auxiliary_columns].copy() if auxiliary_columns else pd.DataFrame()
    sequence_index_export_df = sequence_index_df.drop(columns=auxiliary_columns, errors="ignore")

    write_parquet_file(sequence_rows_df, v6_dir / "sequence_rows.parquet", engine=parquet_engine)
    write_csv_file(sequence_rows_df, v6_dir / "sequence_rows.csv")
    write_csv_file(chunk_manifest_df, v6_dir / "chunk_manifest.csv")
    write_csv_file(discarded_chunks_df, v6_dir / "discarded_chunks.csv")
    write_csv_file(event_fragment_registry_df, v6_dir / "event_fragment_registry.csv")
    write_csv_file(original_event_distribution_df, v6_dir / "original_event_distribution.csv")
    write_csv_file(day_distribution_df, v6_dir / "day_distribution.csv")
    write_csv_file(chunk_distribution_df, v6_dir / "chunk_distribution.csv")
    write_csv_file(split_group_manifest_df, v6_dir / "split_group_manifest.csv")
    write_json_file(v6_dir / "original_event_integrity.json", original_event_integrity_payload)
    write_json_file(v6_dir / "threshold_manifest.json", threshold_manifest_payload)

    write_parquet_file(x_df, v6_dir / "X.parquet", engine=parquet_engine)
    write_csv_file(x_df, v6_dir / "X.csv")
    write_parquet_file(y_df, v6_dir / "y.parquet", engine=parquet_engine)
    write_csv_file(y_df, v6_dir / "y.csv")
    write_parquet_file(sequence_index_export_df, v6_dir / "sequence_index.parquet", engine=parquet_engine)
    write_csv_file(sequence_index_export_df, v6_dir / "sequence_index.csv")
    if not auxiliary_df.empty:
        write_parquet_file(auxiliary_df, v6_dir / "auxiliary_features.parquet", engine=parquet_engine)
        write_csv_file(auxiliary_df, v6_dir / "auxiliary_features.csv")
