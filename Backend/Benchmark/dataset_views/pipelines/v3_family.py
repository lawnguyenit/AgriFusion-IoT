from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from Backend.Benchmark.dataset_views.configs import (
    TAXONOMY_VERSION,
    V3_BOUNDARY_RESET_COLUMNS,
    V3_CONTINUITY_POLICY_VERSION,
    V3_CONTINUITY_THRESHOLD_MULTIPLIER,
    V3_LEGACY_EVENT_CSV_PATH,
    load_operational_lineage_specs,
)
from Backend.Benchmark.dataset_views.continuity import attach_continuity_chunks
from Backend.Benchmark.dataset_views.contracts import TaxonomyEntry, ViewDefinition, ViewSelectionResult
from Backend.Benchmark.dataset_views.lineage import (
    build_event_registry,
    build_derived_view,
    build_direct_view,
    build_evidence_ledger,
    build_independent_view,
    build_pre_onset_artifacts,
    build_v3_metadata_frame,
    build_view_feature_catalog,
    load_unresolved_specs,
    reduce_duplicate_features,
)
from Backend.Benchmark.dataset_views.loaders import bridge_legacy_event_labels
from Backend.Benchmark.dataset_views.reports import build_generation_report_markdown, build_quality_report
from Backend.Benchmark.dataset_views.validators import (
    hash_dataframe_rows,
    stable_hash_object,
    validate_metadata_separation,
    validate_row_alignment,
)
from Backend.Benchmark.dataset_views.writers import write_csv_file, write_json_file, write_parquet_file

from .shared_outputs import utc_now_iso


def prepare_v3_family_context(
    *,
    legacy_event_csv_path: Path | None,
    canonical_df: pd.DataFrame,
    catalog_index: dict[str, object],
    segment_manifest_payload: dict[str, object],
    shared_dir: Path,
    reports_dir: Path,
    parquet_engine: str,
    source_manifest_payload: dict[str, object],
) -> dict[str, Any]:
    continuity_df = attach_continuity_chunks(
        canonical_df,
        segment_manifest=segment_manifest_payload,
        boundary_columns=V3_BOUNDARY_RESET_COLUMNS,
        threshold_multiplier=V3_CONTINUITY_THRESHOLD_MULTIPLIER,
    )
    event_csv_path = (legacy_event_csv_path or V3_LEGACY_EVENT_CSV_PATH).resolve()
    bridge_result = bridge_legacy_event_labels(continuity_df, event_csv_path=event_csv_path)
    event_artifacts = build_event_registry(bridge_result.enriched_canonical_df)
    pre_onset_artifacts = build_pre_onset_artifacts(event_artifacts.enriched_canonical_df)
    lineage_specs = load_operational_lineage_specs()
    lineage_specs.update(load_unresolved_specs(list(canonical_df.columns), lineage_specs))

    direct_artifacts = build_direct_view(pre_onset_artifacts.enriched_canonical_df, lineage_specs)
    derived_artifacts = build_derived_view(pre_onset_artifacts.enriched_canonical_df, lineage_specs)
    independent_artifacts = build_independent_view(pre_onset_artifacts.enriched_canonical_df, lineage_specs)
    reduced_derived_frame, derived_reduction_report = reduce_duplicate_features(derived_artifacts.feature_frame)
    if derived_reduction_report["dropped_feature_count"]:
        derived_artifacts = type(derived_artifacts)(
            feature_frame=reduced_derived_frame,
            audit_frame=derived_artifacts.audit_frame,
            generated_specs=derived_artifacts.generated_specs,
        )

    generated_specs = dict(lineage_specs)
    generated_specs.update(direct_artifacts.generated_specs)
    generated_specs.update(derived_artifacts.generated_specs)
    generated_specs.update(independent_artifacts.generated_specs)

    pre_onset_feature_names = [
        feature_name
        for feature_name, spec in generated_specs.items()
        if spec.allowed_in_v3_pre_onset and feature_name in independent_artifacts.feature_frame.columns
    ]
    pre_onset_feature_frame = independent_artifacts.feature_frame.loc[:, pre_onset_feature_names].copy()
    pre_onset_view_specs = {
        feature_name: generated_specs[feature_name]
        for feature_name in pre_onset_feature_names
    }
    v3_metadata_df = build_v3_metadata_frame(pre_onset_artifacts.enriched_canonical_df)

    evidence_ledger_df = build_evidence_ledger(
        canonical_df=pre_onset_artifacts.enriched_canonical_df,
        known_specs=generated_specs,
        generated_feature_frames={
            "v3_direct": direct_artifacts.feature_frame,
            "v3_derived": derived_artifacts.feature_frame,
            "v3_independent": independent_artifacts.feature_frame,
            "v3_pre_onset": pre_onset_feature_frame,
        },
    )
    generation_report_markdown = build_generation_report_markdown(
        evidence_ledger_df=evidence_ledger_df,
        event_registry_df=event_artifacts.event_registry_df,
        pre_onset_y_df=pre_onset_artifacts.y_frame,
        legacy_coverage_report=bridge_result.coverage_report,
    )

    write_csv_file(evidence_ledger_df, shared_dir / "v3_evidence_ledger.csv")
    write_parquet_file(event_artifacts.event_registry_df, shared_dir / "v3_event_registry.parquet", engine=parquet_engine)
    write_csv_file(event_artifacts.event_registry_df, shared_dir / "v3_event_registry.csv")
    (reports_dir / "v3_generation_report.md").write_text(generation_report_markdown, encoding="utf-8")

    write_json_file(
        reports_dir / "v3_bridge_report.json",
        {
            "legacy_event_bridge": bridge_result.coverage_report,
            "continuity_policy_version": V3_CONTINUITY_POLICY_VERSION,
            "continuity_threshold_multiplier": V3_CONTINUITY_THRESHOLD_MULTIPLIER,
            "boundary_reset_columns": list(V3_BOUNDARY_RESET_COLUMNS),
        },
    )

    return {
        "canonical_df": pre_onset_artifacts.enriched_canonical_df,
        "metadata_df": v3_metadata_df,
        "catalog_index": catalog_index,
        "source_manifest_payload": source_manifest_payload,
        "evidence_ledger_df": evidence_ledger_df,
        "event_registry_df": event_artifacts.event_registry_df,
        "legacy_coverage_report": bridge_result.coverage_report,
        "artifacts": {
            "v3_direct": direct_artifacts,
            "v3_derived": derived_artifacts,
            "v3_independent": independent_artifacts,
            "v3_pre_onset": {
                "feature_frame": pre_onset_feature_frame,
                "audit_frame": pre_onset_artifacts.target_audit_frame,
                "generated_specs": pre_onset_view_specs,
                "y_frame": pre_onset_artifacts.y_frame,
            },
        },
        "derived_reduction_report": derived_reduction_report,
        "parquet_engine": parquet_engine,
    }


def materialize_v3_view(
    *,
    taxonomy_entry: TaxonomyEntry,
    view_definition: ViewDefinition,
    v3_context: dict[str, Any],
    output_dir: Path,
    parquet_engine: str,
    source_manifest_payload: dict[str, object],
) -> None:
    metadata_df: pd.DataFrame = v3_context["metadata_df"]
    catalog_index: dict[str, object] = v3_context["catalog_index"]
    payload = v3_context["artifacts"][view_definition.view_id]
    if isinstance(payload, dict):
        feature_frame = payload["feature_frame"]
        audit_frame = payload["audit_frame"]
        generated_specs = payload["generated_specs"]
        y_frame = payload["y_frame"]
    else:
        feature_frame = payload.feature_frame
        audit_frame = payload.audit_frame
        generated_specs = payload.generated_specs
        y_frame = None

    feature_names = list(feature_frame.columns)
    validate_metadata_separation(metadata_columns=list(metadata_df.columns), feature_columns=feature_names, label_columns=[])
    validate_row_alignment(
        reference_length=len(metadata_df),
        candidate_length=len(feature_frame),
        artifact_name=f"{view_definition.view_id}/X.parquet",
    )
    if audit_frame is not None:
        validate_row_alignment(
            reference_length=len(metadata_df),
            candidate_length=len(audit_frame),
            artifact_name=f"{view_definition.view_id}/operational_window_audit.parquet",
        )
    if y_frame is not None:
        validate_row_alignment(
            reference_length=len(metadata_df),
            candidate_length=len(y_frame),
            artifact_name=f"{view_definition.view_id}/y.parquet",
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    write_parquet_file(feature_frame, output_dir / "X.parquet", engine=parquet_engine)
    write_csv_file(feature_frame, output_dir / "X.csv")
    write_parquet_file(metadata_df, output_dir / "metadata.parquet", engine=parquet_engine)
    write_csv_file(metadata_df, output_dir / "metadata.csv")
    feature_catalog_df = build_view_feature_catalog(feature_names, generated_specs)
    write_csv_file(feature_catalog_df, output_dir / "feature_catalog.csv")
    if audit_frame is not None:
        audit_name = "target_audit" if view_definition.view_id == "v3_pre_onset" else "operational_window_audit"
        write_parquet_file(audit_frame, output_dir / f"{audit_name}.parquet", engine=parquet_engine)
        write_csv_file(audit_frame, output_dir / f"{audit_name}.csv")
    if y_frame is not None:
        write_parquet_file(y_frame, output_dir / "y.parquet", engine=parquet_engine)
        write_csv_file(y_frame, output_dir / "y.csv")

    selection = ViewSelectionResult(
        view_definition=view_definition,
        ordered_features=tuple(feature_names),
    )
    quality_report = build_quality_report(
        view_id=view_definition.view_id,
        feature_frame=feature_frame,
        selection=selection,
        catalog_index=catalog_index,
    )
    schema_payload = {
        "view_id": view_definition.view_id,
        "row_count": int(len(feature_frame)),
        "feature_count": int(feature_frame.shape[1]),
        "columns": [{"name": column, "dtype": str(dtype)} for column, dtype in feature_frame.dtypes.items()],
    }
    manifest_payload = {
        "view_name": view_definition.view_id,
        "purpose": view_definition.description,
        "source_files": {
            "canonical_history": source_manifest_payload["source"]["canonical_history_path"],
            "feature_catalog": source_manifest_payload["source"]["feature_catalog_path"],
            "legacy_event_csv": v3_context["legacy_coverage_report"]["event_csv_path"],
        },
        "source_hashes": {
            "canonical_history_hash": source_manifest_payload["source"]["canonical_history_hash"],
            "source_schema_hash": source_manifest_payload["source"]["source_schema_hash"],
            "feature_catalog_hash": source_manifest_payload["source"]["feature_catalog_hash"],
        },
        "row_count": int(len(feature_frame)),
        "feature_count": int(feature_frame.shape[1]),
        "ordered_feature_list": feature_names,
        "genealogy_groups_included": v3_genealogy_groups(view_definition.view_id),
        "genealogy_groups_excluded": v3_excluded_genealogy_groups(view_definition.view_id),
        "causal": True,
        "segment_aware": True,
        "continuity_reset": True,
        "synthetic_rows": False,
        "imputation": "none",
        "window_definitions": v3_window_definition(view_definition.view_id),
        "minimum_evidence_policy": v3_minimum_evidence_policy(view_definition.view_id),
        "label_columns_excluded": ["event_*", "event_primary", "big_label", "binary", "tri_class", "four_class"],
        "future_fields_excluded": True,
        "generated_at": utc_now_iso(),
        "code_version": TAXONOMY_VERSION,
        "metadata_columns": list(metadata_df.columns),
        "ordered_feature_list_hash": stable_hash_object(feature_names),
        "x_data_hash": hash_dataframe_rows(feature_frame),
        "debug_csv_paths": {
            "feature_matrix_csv": str((output_dir / "X.csv").resolve()),
            "metadata_csv": str((output_dir / "metadata.csv").resolve()),
            "feature_catalog_csv": str((output_dir / "feature_catalog.csv").resolve()),
        },
    }
    if view_definition.view_id == "v3_derived":
        manifest_payload["feature_reduction"] = v3_context.get("derived_reduction_report", {})
    if audit_frame is not None:
        audit_name = "target_audit" if view_definition.view_id == "v3_pre_onset" else "operational_window_audit"
        manifest_payload["debug_csv_paths"][audit_name + "_csv"] = str((output_dir / f"{audit_name}.csv").resolve())
    if y_frame is not None:
        manifest_payload["debug_csv_paths"]["y_csv"] = str((output_dir / "y.csv").resolve())

    write_json_file(output_dir / "manifest.json", manifest_payload)
    write_json_file(output_dir / "schema.json", schema_payload)
    write_json_file(output_dir / "quality_report.json", quality_report)


def v3_genealogy_groups(view_id: str) -> list[str]:
    mapping = {
        "v3_direct": ["direct_rule"],
        "v3_derived": ["derived_rule"],
        "v3_independent": ["independent_process"],
        "v3_pre_onset": ["independent_process"],
    }
    return mapping[view_id]


def v3_excluded_genealogy_groups(view_id: str) -> list[str]:
    groups = {"direct_rule", "derived_rule", "independent_process", "unresolved"}
    return sorted(groups.difference(v3_genealogy_groups(view_id)))


def v3_window_definition(view_id: str) -> dict[str, object]:
    if view_id == "v3_direct":
        return {"window_type": "none", "continuity_policy_version": V3_CONTINUITY_POLICY_VERSION}
    if view_id in {"v3_derived", "v3_independent"}:
        return {
            "window_type": "cycle_based",
            "horizons": ["3c", "6c", "12c"],
            "continuity_policy_version": V3_CONTINUITY_POLICY_VERSION,
            "boundary_reset_columns": list(V3_BOUNDARY_RESET_COLUMNS),
            "threshold_multiplier": V3_CONTINUITY_THRESHOLD_MULTIPLIER,
        }
    return {
        "window_type": "future_horizon_cycles",
        "horizons": ["1c", "3c", "6c"],
        "continuity_policy_version": V3_CONTINUITY_POLICY_VERSION,
        "boundary_reset_columns": list(V3_BOUNDARY_RESET_COLUMNS),
        "threshold_multiplier": V3_CONTINUITY_THRESHOLD_MULTIPLIER,
    }


def v3_minimum_evidence_policy(view_id: str) -> dict[str, object]:
    if view_id == "v3_direct":
        return {"policy": "current_row_only"}
    if view_id == "v3_derived":
        return {"cycle_horizons": {"3c": 2, "6c": 3, "12c": 5}}
    if view_id == "v3_independent":
        return {"cycle_horizons": {"3c": 2, "6c": 3, "12c": 5}, "slope_min_observations": 3}
    return {
        "target_horizons": ["1c", "3c", "6c"],
        "negative_requires_full_future_coverage": True,
        "excluded_when_missing_event_context": True,
    }
