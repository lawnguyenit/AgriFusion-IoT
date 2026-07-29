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
    build_excluded_samples_audit,
    build_label_dependency_registry,
    build_label_distribution,
    build_label_examples,
    build_label_overlap_matrix,
    build_label_registry,
    build_run_manifest,
)
from Backend.Benchmark.weak_labels.runtime.contracts import LabelArtifactBundle, WeakLabelsConfig, WeakLabelsResult
from Backend.Benchmark.weak_labels.shared import build_split_assignment_frame
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
    split_bundle = build_base_split_bundle(
        canonical_df,
        train_ratio=config.train_ratio,
        validation_ratio=config.validation_ratio,
        test_ratio=config.test_ratio,
        base_split_strategy=config.base_split_strategy,
        run_profile=config.run_profile,
    )
    continuity_df = canonical_df.merge(
        split_bundle.assignments_df[["record.id", "base_partition", "split.boundary_before", "base_partition_index"]],
        on="record.id",
        how="left",
        validate="one_to_one",
    )
    continuity_df = attach_continuity_chunks(
        continuity_df,
        segment_manifest=segment_manifest,
        boundary_columns=("record.segment_boundary_before", "split.boundary_before"),
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
        boundary_timestamps=split_bundle.boundary_timestamps,
    )

    point_split_assignments = build_split_assignment_frame(point_artifacts.point_labels_train)
    view_split_assignments = build_split_assignment_frame(
        point_artifacts.point_labels_train,
        v2_artifacts.same_y_labels,
        v2_artifacts.temporal_labels_3h,
        v2_artifacts.temporal_labels_8h,
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
        base_split_assignments=split_bundle.assignments_df.convert_dtypes(),
        view_split_assignments=view_split_assignments,
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
        split_manifest=split_bundle.split_manifest,
        run_manifest={},
        label_registry=build_label_registry(),
    )

    _write_bundle(bundle, output_dir=output_dir, parquet_engine=parquet_engine)
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
    write_json_file(output_dir / "run_manifest.json", run_manifest)
    return WeakLabelsResult(
        run_id=run_id,
        output_dir=output_dir,
        row_count=int(len(canonical_df)),
        generated_files=PRIMARY_OUTPUT_FILES,
    )


def _write_bundle(bundle: LabelArtifactBundle, *, output_dir: Path, parquet_engine: str) -> None:
    write_parquet(bundle.point_evidence_flags, output_dir / "point_evidence_flags.parquet", engine=parquet_engine)
    write_parquet(bundle.point_labels_detailed, output_dir / "point_labels_detailed.parquet", engine=parquet_engine)
    write_parquet(bundle.point_labels_train, output_dir / "point_labels_train.parquet", engine=parquet_engine)
    write_parquet(bundle.technical_labels_audit, output_dir / "technical_labels_audit.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_same_y_labels, output_dir / "v2_same_y_labels.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_evidence_3h, output_dir / "v2_temporal_evidence_3h.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_evidence_8h, output_dir / "v2_temporal_evidence_8h.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_labels_3h, output_dir / "v2_temporal_labels_3h.parquet", engine=parquet_engine)
    write_parquet(bundle.v2_temporal_labels_8h, output_dir / "v2_temporal_labels_8h.parquet", engine=parquet_engine)
    write_parquet(bundle.base_split_assignments, output_dir / "base_split_assignments.parquet", engine=parquet_engine)
    write_parquet(bundle.view_split_assignments, output_dir / "view_split_assignments.parquet", engine=parquet_engine)
    write_parquet(bundle.matched_cohort_manifest, output_dir / "matched_cohort_manifest.parquet", engine=parquet_engine)
    write_csv(bundle.label_dependency_registry, output_dir / "label_dependency_registry.csv")
    write_csv(bundle.label_distribution, output_dir / "label_distribution.csv")
    write_csv(bundle.label_overlap_matrix, output_dir / "label_overlap_matrix.csv")
    write_csv(bundle.threshold_sensitivity, output_dir / "threshold_sensitivity.csv")
    write_csv(bundle.excluded_samples_audit, output_dir / "excluded_samples_audit.csv")
    write_csv(bundle.label_examples, output_dir / "label_examples.csv")
    write_json_file(output_dir / "split_manifest.json", bundle.split_manifest)
    write_yaml_file(output_dir / "label_registry.yaml", bundle.label_registry)
    write_csv(bundle.v2_label_agreement_3h_8h, output_dir / "v2_label_agreement_3h_8h.csv")


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
