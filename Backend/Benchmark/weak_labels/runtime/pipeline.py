from __future__ import annotations

from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.continuity import attach_continuity_chunks
from Backend.Benchmark.dataset_views.validators import ensure_parquet_engine, validate_unique_record_ids
from Backend.Benchmark.shared.artifacts import create_run_directory
from Backend.Benchmark.weak_labels.io import (
    load_canonical_history,
    load_feature_catalog,
    load_json_payload,
    resolve_segment_manifest_path,
    write_csv,
    write_json_file,
    write_parquet,
    write_yaml_file,
)
from Backend.Benchmark.weak_labels.partitions import build_base_split_bundle
from Backend.Benchmark.weak_labels.point import (
    build_applicability_frame,
    build_point_label_artifacts,
    build_threshold_context,
    enrich_point_continuity_features,
)
from Backend.Benchmark.weak_labels.reporting import (
    build_artifact_guide_markdown,
    build_current_scope_summary,
    build_excluded_samples_audit,
    build_label_dependency_registry,
    build_label_distribution,
    build_label_examples,
    build_label_overlap_matrix,
    build_label_registry,
    build_run_manifest,
)
from Backend.Benchmark.weak_labels.reporting.tranche0_contracts import build_tranche0_audit_artifacts
from Backend.Benchmark.weak_labels.runtime.contracts import LabelArtifactBundle, WeakLabelsConfig, WeakLabelsResult
from Backend.Benchmark.weak_labels.runtime.layout import (
    build_artifact_catalog,
    build_weak_labels_artifact_layout,
)
from Backend.Benchmark.weak_labels.shared.configs import PRIMARY_OUTPUT_FILES
from Backend.Benchmark.weak_labels.v2 import build_v2_label_artifacts


def build_weak_labels(config: WeakLabelsConfig) -> WeakLabelsResult:
    parquet_engine = ensure_parquet_engine()
    canonical_df = load_canonical_history(config.canonical_history_path.resolve())
    validate_unique_record_ids(canonical_df, key_column="record.id")
    _ = load_feature_catalog(config.feature_catalog_path.resolve())
    segment_manifest_path = resolve_segment_manifest_path(
        manifest_path=config.manifest_path.resolve() if config.manifest_path is not None else None,
        segment_manifest_path=config.segment_manifest_path.resolve() if config.segment_manifest_path is not None else None,
    )
    segment_manifest = load_json_payload(segment_manifest_path)

    run_id, output_dir = create_run_directory(config.output_root.resolve(), prefix="weak_labels")
    layout = build_weak_labels_artifact_layout(output_dir)
    layout.create()
    split_bundle = build_base_split_bundle(
        canonical_df,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        base_split_strategy=config.base_split_strategy,
        run_profile=config.run_profile,
    )
    continuity_df = canonical_df.merge(
        split_bundle.assignments_df[["record.id", "base_partition", "base_partition_index"]],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    continuity_df = attach_continuity_chunks(
        continuity_df,
        segment_manifest=segment_manifest,
        boundary_columns=("record.segment_boundary_before",),
        threshold_multiplier=2.5,
    )
    applicability_df = build_applicability_frame(continuity_df)
    continuity_df = continuity_df.merge(
        applicability_df.drop(
            columns=["record.ts_sample", "record.segment_id", "record.node_id", "npk.valid", "sht.valid"],
            errors="ignore",
        ),
        on="record.id",
        how="left",
    )
    continuity_df = enrich_point_continuity_features(continuity_df)
    threshold_context = build_threshold_context(continuity_df, threshold_mode=config.threshold_mode)
    point_artifacts = build_point_label_artifacts(continuity_df, threshold_context=threshold_context)
    v2_artifacts = build_v2_label_artifacts(
        point_artifacts.enriched_df,
        segment_manifest=segment_manifest,
    )

    bundle = LabelArtifactBundle(
        point_evidence_flags=point_artifacts.point_evidence_flags,
        point_labels_detailed=point_artifacts.point_labels_detailed,
        point_labels_train=point_artifacts.point_labels_train,
        technical_labels_audit=point_artifacts.technical_labels_audit,
        v2_same_y_labels=v2_artifacts.same_y_labels,
        v2_temporal_evidence_3h=v2_artifacts.temporal_evidence_3h,
        v2_temporal_evidence_8h=v2_artifacts.temporal_evidence_8h,
        v2_temporal_labels_3h=v2_artifacts.temporal_labels_3h,
        v2_temporal_labels_8h=v2_artifacts.temporal_labels_8h,
        matched_cohort_manifest=v2_artifacts.matched_cohort_manifest,
        label_dependency_registry=build_label_dependency_registry(),
        label_distribution=build_label_distribution(
            point_artifacts.point_labels_train,
            v2_artifacts.same_y_labels,
            v2_artifacts.temporal_labels_3h,
            v2_artifacts.temporal_labels_8h,
        ),
        label_overlap_matrix=build_label_overlap_matrix(
            point_artifacts.point_labels_train,
            v2_artifacts.same_y_labels,
            v2_artifacts.temporal_labels_3h,
            v2_artifacts.temporal_labels_8h,
        ),
        threshold_sensitivity=threshold_context.sensitivity_df,
        excluded_samples_audit=build_excluded_samples_audit(
            point_artifacts.point_labels_detailed,
            point_artifacts.point_labels_train,
            v2_artifacts.same_y_labels,
            v2_artifacts.temporal_labels_3h,
            v2_artifacts.temporal_labels_8h,
        ),
        label_examples=build_label_examples(
            point_artifacts.point_labels_train,
            v2_artifacts.temporal_labels_3h,
            v2_artifacts.temporal_labels_8h,
        ),
        v2_label_agreement_3h_8h=v2_artifacts.label_agreement_3h_8h,
        run_manifest={},
        label_registry=build_label_registry(),
    )
    tranche0_audits = build_tranche0_audit_artifacts(
        point_enriched_df=point_artifacts.enriched_df,
        point_labels_detailed=point_artifacts.point_labels_detailed,
        v2_same_y_labels=v2_artifacts.same_y_labels,
        v2_temporal_labels_3h=v2_artifacts.temporal_labels_3h,
        v2_temporal_labels_8h=v2_artifacts.temporal_labels_8h,
        v2_temporal_evidence_3h=v2_artifacts.temporal_evidence_3h,
        v2_temporal_evidence_8h=v2_artifacts.temporal_evidence_8h,
        threshold_records=threshold_context.threshold_records,
        weak_labels_repo_root=Path(__file__).resolve().parents[4],
    )
    bundle.label_assignment = tranche0_audits["label_assignment"]
    bundle.rule_firings = tranche0_audits["rule_firings"]
    bundle.rule_registry = tranche0_audits["rule_registry"]
    bundle.threshold_registry = tranche0_audits["threshold_registry"]
    bundle.label_source_dependency = tranche0_audits["label_source_dependency"]

    _write_bundle(bundle, output_dir=output_dir, layout=layout, parquet_engine=parquet_engine)
    run_manifest = build_run_manifest(
        config_dict=_config_to_dict(config),
        canonical_path=config.canonical_history_path.resolve(),
        feature_catalog_path=config.feature_catalog_path.resolve(),
        segment_manifest_path=segment_manifest_path.resolve(),
        canonical_df=canonical_df,
        output_dir=output_dir,
        split_manifest=split_bundle.split_manifest,
        threshold_records=[record.__dict__ for record in threshold_context.threshold_records],
    )
    run_manifest["artifact_layout_version"] = "weak_labels.layout.v2"
    write_json_file(layout.run_metadata / "run_manifest.json", run_manifest)
    write_json_file(layout.run_metadata / "current_scope_summary.json", build_current_scope_summary())
    write_csv(pd.DataFrame(build_artifact_catalog(layout)).convert_dtypes(), layout.run_metadata / "artifact_catalog.csv")
    (output_dir / "ARTIFACT_GUIDE.md").write_text(build_artifact_guide_markdown() + "\n", encoding="utf-8")
    return WeakLabelsResult(
        run_id=run_id,
        output_dir=output_dir,
        row_count=int(len(canonical_df)),
        generated_files=PRIMARY_OUTPUT_FILES,
    )


def _write_bundle(bundle: LabelArtifactBundle, *, output_dir: Path, layout, parquet_engine: str) -> None:
    write_parquet(bundle.point_evidence_flags, layout.point / "point_evidence_flags.parquet", engine=parquet_engine)
    write_parquet(bundle.point_labels_detailed, layout.point / "point_labels_detailed.parquet", engine=parquet_engine)
    write_parquet(bundle.point_labels_train, layout.point / "point_labels_train.parquet", engine=parquet_engine)
    write_parquet(bundle.technical_labels_audit, layout.point / "technical_labels_audit.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_same_y_labels, layout.v2 / "v2_same_y_labels.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_evidence_3h, layout.v2 / "v2_temporal_evidence_3h.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_evidence_8h, layout.v2 / "v2_temporal_evidence_8h.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_labels_3h, layout.v2 / "v2_temporal_labels_3h.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_labels_8h, layout.v2 / "v2_temporal_labels_8h.parquet", engine=parquet_engine)
    write_parquet(bundle.matched_cohort_manifest, layout.v2 / "matched_cohort_manifest.parquet", engine=parquet_engine)
    write_csv(bundle.label_dependency_registry, layout.registries / "label_dependency_registry.csv")
    write_csv(bundle.label_distribution, layout.audits / "label_distribution.csv")
    write_csv(bundle.label_overlap_matrix, layout.audits / "label_overlap_matrix.csv")
    write_csv(bundle.threshold_sensitivity, layout.threshold_diagnostics / "threshold_sensitivity.csv")
    write_csv(bundle.excluded_samples_audit, layout.audits / "excluded_samples_audit.csv")
    write_csv(bundle.label_examples, layout.audits / "label_examples.csv")
    write_yaml_file(layout.registries / "label_registry.yaml", bundle.label_registry)
    write_csv(bundle.v2_label_agreement_3h_8h, layout.v2 / "v2_label_agreement_3h_8h.csv")
    if bundle.label_assignment is not None:
        write_parquet(bundle.label_assignment, layout.audit / "label_assignment.parquet", engine=parquet_engine)
    if bundle.rule_firings is not None:
        write_parquet(bundle.rule_firings, layout.audit / "rule_firings.parquet", engine=parquet_engine)
    if bundle.rule_registry is not None:
        write_csv(bundle.rule_registry, layout.audit / "rule_registry.csv")
    if bundle.threshold_registry is not None:
        write_csv(bundle.threshold_registry, layout.audit / "threshold_registry.csv")
    if bundle.label_source_dependency is not None:
        write_csv(bundle.label_source_dependency, layout.audit / "label_source_dependency.csv")


def _config_to_dict(config: WeakLabelsConfig) -> dict[str, object]:
    return {
        "canonical_history_path": str(config.canonical_history_path),
        "feature_catalog_path": str(config.feature_catalog_path),
        "manifest_path": str(config.manifest_path) if config.manifest_path is not None else None,
        "segment_manifest_path": str(config.segment_manifest_path) if config.segment_manifest_path is not None else None,
        "output_root": str(config.output_root),
        "train_ratio": config.train_ratio,
        "validation_ratio": config.validation_ratio,
        "test_ratio": config.test_ratio,
        "base_split_strategy": config.base_split_strategy,
        "run_profile": config.run_profile,
        "threshold_mode": config.threshold_mode,
        "split_gap_minutes_override": config.split_gap_minutes_override,
        "random_seed": config.random_seed,
    }
