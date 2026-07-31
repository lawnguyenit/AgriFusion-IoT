from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.provenance import resolve_code_commit
from Backend.Benchmark.protocol_registry import authorize_operation, load_protocol_registry
from Backend.Benchmark.dataset_views.continuity import attach_continuity_chunks
from Backend.Benchmark.dataset_views.continuity.chunks import build_segment_cadence_index
from Backend.Benchmark.dataset_views.validators import ensure_parquet_engine, stable_hash_object, validate_unique_record_ids
from Backend.Benchmark.evaluation_protocols.diagnostics import (
    annotate_core_fold_status,
    build_calendar_blocks,
    build_cross_position_feature_shift_isr,
    build_cross_position_feature_shift_raw,
    build_cross_position_label_transport,
    build_dependency_artifacts,
    build_estimability_artifacts,
    build_fold_quality_manifest,
    build_p1_5day_support_diagnostic,
    build_p1_rolling_fold_specs,
    build_representation_validity_artifacts,
    build_threshold_sensitivity_transport,
    build_v2_coverage_artifacts,
)
from Backend.Benchmark.evaluation_protocols.domains import (
    DEPLOYMENT_DOMAIN_MAP,
    build_deployment_domain_frame,
    build_protocol_config_hash,
    load_native_thresholds,
)
from Backend.Benchmark.evaluation_protocols.lineage import (
    build_explicit_matched_cohort_artifacts,
    build_primary_protocol_artifacts,
    build_protocol_assignment_artifacts,
)
from Backend.Benchmark.evaluation_protocols.contracts import (
    EvaluationProtocolConfig,
    EvaluationProtocolResult,
)
from Backend.Benchmark.evaluation_protocols.pipeline.layout import (
    build_artifact_catalog,
    build_evaluation_artifact_layout,
)
from Backend.Benchmark.evaluation_protocols.pipeline.guides import write_artifact_guides
from Backend.Benchmark.evaluation_protocols.pipeline.tranche0_contracts import (
    build_claim_registry,
    build_comparison_registry,
    build_e1_fold_registry,
    build_environment_registry,
    build_experiment_registry,
    build_legacy_to_v2_equivalence_report,
    build_runner_contract_v2_payload,
    build_sample_environment_manifest,
    extend_manifest_with_contracts,
)
from Backend.Benchmark.evaluation_protocols.pipeline.consumption import (
    build_comparison_training_manifest,
    load_dataset_view_feature_artifacts,
    build_task_training_manifest,
    build_task_view_registry,
    load_native_label_sources,
)
from Backend.Benchmark.evaluation_protocols.pipeline.frozen_target import build_frozen_target_manifest
from Backend.Benchmark.evaluation_protocols.scope import PRIMARY_FEATURE_SOURCE_VIEW_IDS, PRIMARY_FEATURE_VIEW_IDS
from Backend.Benchmark.shared.artifacts import create_run_directory
from Backend.Benchmark.weak_labels.infrastructure.io import (
    load_canonical_history,
    load_feature_catalog,
    load_json_payload,
    resolve_segment_manifest_path,
    write_csv,
    write_json_file,
    write_parquet,
    write_yaml_file,
)
from Backend.Benchmark.weak_labels.infrastructure.hashing import file_sha256


def build_evaluation_protocols(config: EvaluationProtocolConfig) -> EvaluationProtocolResult:
    protocol_registry = load_protocol_registry(config.protocol_registry_run_dir)
    _validate_protocol_registry_authority(config, protocol_registry)
    parquet_engine = ensure_parquet_engine()
    canonical_df = load_canonical_history(config.canonical_history_path.resolve())
    validate_unique_record_ids(canonical_df, key_column="record.id")
    _ = load_feature_catalog(config.feature_catalog_path.resolve())
    segment_manifest_path = resolve_segment_manifest_path(
        manifest_path=config.manifest_path.resolve(),
        segment_manifest_path=config.segment_manifest_path.resolve() if config.segment_manifest_path is not None else None,
    )
    segment_manifest = load_json_payload(segment_manifest_path)

    run_id, output_dir = create_run_directory(config.output_root.resolve(), prefix="evaluation_protocols")
    layout = build_evaluation_artifact_layout(output_dir)
    layout.create()

    working = canonical_df.copy()
    working["deployment_domain_name"] = working["record.segment_id"].astype("string").map(DEPLOYMENT_DOMAIN_MAP).fillna("UNKNOWN")
    working["base_partition"] = "protocol_all"
    working = attach_continuity_chunks(
        working,
        segment_manifest=segment_manifest,
        boundary_columns=("record.segment_boundary_before",),
        threshold_multiplier=2.5,
    )
    deployment_domains = build_deployment_domain_frame(
        working,
        segment_manifest=segment_manifest,
        mapping_version="2026-07-16.eval-protocol.v1",
    )
    write_csv(deployment_domains, layout.domain_manifests / "deployment_domains.csv")
    environment_registry = build_environment_registry(
        working,
        protocol_registry.environment_manifest,
    )
    sample_environment_manifest = build_sample_environment_manifest(working, environment_registry)
    write_csv(environment_registry, layout.domain_manifests / "environment_registry.csv")
    write_parquet(sample_environment_manifest, layout.domain_manifests / "sample_environment_manifest.parquet", engine=parquet_engine)

    p1_df = working.loc[working["deployment_domain_name"].astype("string") == "P1_SOURCE"].copy()
    p2_df = working.loc[working["deployment_domain_name"].astype("string") == "P2_TARGET"].copy()
    cadence_by_segment = build_segment_cadence_index(segment_manifest)
    p1_segment_id = str(p1_df["record.segment_id"].astype("string").dropna().iloc[0])
    expected_interval_sec = int(cadence_by_segment[p1_segment_id])
    blocks5_df = build_calendar_blocks(p1_df, block_days=5, expected_interval_sec=expected_interval_sec)
    fold_specs_5day = build_p1_rolling_fold_specs(
        blocks5_df,
        initial_train_blocks=config.initial_train_blocks,
        validation_blocks=config.validation_blocks,
        test_blocks=config.test_blocks,
        fold_policy_id="E1_DIAGNOSTIC_5D_V1",
    )
    blocks7_df = build_calendar_blocks(p1_df, block_days=config.rolling_block_days, expected_interval_sec=expected_interval_sec)
    fold_specs = build_p1_rolling_fold_specs(
        blocks7_df,
        initial_train_blocks=config.initial_train_blocks,
        validation_blocks=config.validation_blocks,
        test_blocks=config.test_blocks,
        fold_policy_id="E1_PRIMARY_7D_V1",
    )
    native_thresholds = load_native_thresholds(config.native_label_release_dir)
    sensitivity_df = native_thresholds.sensitivity_df
    threshold_manifest = {
        "threshold_id": "native_frozen_q10",
        "policy": "READ_NATIVE_RELEASE_ONLY",
        "threshold_value": native_thresholds.q10,
        "native_label_release_dir": str(config.native_label_release_dir.resolve()),
        "native_label_release_manifest": native_thresholds.manifest,
        "code_commit": resolve_code_commit(Path(__file__).resolve().parents[4]),
    }
    threshold_manifest["config_hash"] = build_protocol_config_hash(_config_to_dict(config))
    write_csv(pd.DataFrame([threshold_manifest]).convert_dtypes(), layout.threshold_policy / "primary_frozen_initial_source.csv")
    write_csv(sensitivity_df, layout.threshold_policy / "threshold_sensitivity_diagnostic.csv")
    threshold_manifest_hash = stable_hash_object(threshold_manifest)

    weak_sources = load_native_label_sources(config.native_label_release_dir.resolve())
    feature_artifacts = load_dataset_view_feature_artifacts(
        config.dataset_views_run_dir.resolve(),
        required_view_ids=PRIMARY_FEATURE_SOURCE_VIEW_IDS,
    )

    point_labels = weak_sources.point_labels_train.loc[
        weak_sources.point_labels_train["task_id"].isin(["v0_point_train", "v1_point_train"])
    ].copy()
    record_domain_lookup = working.set_index("record.id")["deployment_domain_name"].astype("string").to_dict()
    point_labels["deployment_domain_name"] = point_labels["sample_id"].astype("string").map(record_domain_lookup)
    v2_same_y = weak_sources.v2_same_y_labels.copy()
    v2_same_y["deployment_domain_name"] = v2_same_y["sample_id"].astype("string").map(record_domain_lookup)
    v2_temporal_3h = weak_sources.v2_temporal_labels_3h.copy()
    v2_temporal_3h["deployment_domain_name"] = v2_temporal_3h["sample_id"].astype("string").map(record_domain_lookup)
    v2_temporal_8h = weak_sources.v2_temporal_labels_8h.copy()
    v2_temporal_8h["deployment_domain_name"] = v2_temporal_8h["sample_id"].astype("string").map(record_domain_lookup)
    assignment_artifacts_7day = build_protocol_assignment_artifacts(
        fold_specs=fold_specs,
        point_labels=point_labels,
        v2_same_y=v2_same_y,
        v2_temporal_3h=v2_temporal_3h,
        v2_temporal_8h=v2_temporal_8h,
        v2_evidence_3h=weak_sources.v2_temporal_evidence_3h,
        v2_evidence_8h=weak_sources.v2_temporal_evidence_8h,
        working=working,
        expected_interval_sec=expected_interval_sec,
    )
    fold_quality_7day = build_fold_quality_manifest(
        fold_specs=fold_specs,
        p1_df=p1_df,
        expected_interval_sec=expected_interval_sec,
        label_frames={
            "v0_point_train": point_labels.loc[point_labels["task_id"] == "v0_point_train"].copy(),
            "v1_point_train": point_labels.loc[point_labels["task_id"] == "v1_point_train"].copy(),
            "v2_same_y_3h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_3h"].copy(),
            "v2_same_y_8h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_8h"].copy(),
            "v2_temporal_3h": v2_temporal_3h.copy(),
            "v2_temporal_8h": v2_temporal_8h.copy(),
        },
        view_assignments=assignment_artifacts_7day.view_split_assignments,
        boundary_event_audit=None,
        block_days=config.rolling_block_days,
        validity_column="core_environment_fully_evaluable",
    )
    assignment_artifacts_5day = build_protocol_assignment_artifacts(
        fold_specs=fold_specs_5day,
        point_labels=point_labels,
        v2_same_y=v2_same_y,
        v2_temporal_3h=v2_temporal_3h,
        v2_temporal_8h=v2_temporal_8h,
        v2_evidence_3h=weak_sources.v2_temporal_evidence_3h,
        v2_evidence_8h=weak_sources.v2_temporal_evidence_8h,
        working=working,
        expected_interval_sec=expected_interval_sec,
    )
    fold_quality_5day = build_fold_quality_manifest(
        fold_specs=fold_specs_5day,
        p1_df=p1_df,
        expected_interval_sec=expected_interval_sec,
        label_frames={
            "v0_point_train": point_labels.loc[point_labels["task_id"] == "v0_point_train"].copy(),
            "v1_point_train": point_labels.loc[point_labels["task_id"] == "v1_point_train"].copy(),
            "v2_same_y_3h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_3h"].copy(),
            "v2_same_y_8h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_8h"].copy(),
            "v2_temporal_3h": v2_temporal_3h.copy(),
            "v2_temporal_8h": v2_temporal_8h.copy(),
        },
        view_assignments=assignment_artifacts_7day.view_split_assignments,
        boundary_event_audit=None,
        block_days=5,
        validity_column="core_environment_fully_evaluable",
    )
    support_5day_df = build_p1_5day_support_diagnostic(
        p1_df,
        expected_interval_sec=expected_interval_sec,
        initial_train_blocks=config.initial_train_blocks,
        validation_blocks=config.validation_blocks,
        test_blocks=config.test_blocks,
        label_frames={
            "v0_point_train": point_labels.loc[point_labels["task_id"] == "v0_point_train"].copy(),
            "v1_point_train": point_labels.loc[point_labels["task_id"] == "v1_point_train"].copy(),
            "v2_same_y_3h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_3h"].copy(),
            "v2_same_y_8h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_8h"].copy(),
            "v2_temporal_3h": v2_temporal_3h.copy(),
            "v2_temporal_8h": v2_temporal_8h.copy(),
        },
        validity_column="core_environment_fully_evaluable",
    )
    fold_quality_5day = annotate_core_fold_status(
        fold_quality_5day,
        assignment_artifacts_5day.unsupported_class_audit,
    )
    fold_quality_7day = annotate_core_fold_status(
        fold_quality_7day,
        assignment_artifacts_7day.unsupported_class_audit,
    )
    write_csv(fold_quality_5day, layout.support_5day / "fold_manifest.csv")
    write_csv(support_5day_df, layout.support_5day / "fold_support_manifest.csv")
    write_parquet(assignment_artifacts_5day.base_split_assignments, layout.support_5day / "base_split_assignments.parquet", engine=parquet_engine)
    write_parquet(assignment_artifacts_5day.view_split_assignments, layout.support_5day / "view_effective_split_assignments.parquet", engine=parquet_engine)
    write_csv(assignment_artifacts_5day.unsupported_class_audit, layout.support_5day / "unsupported_class_audit.csv")
    write_csv(fold_quality_7day, layout.support_7day / "fold_support_manifest.csv")
    write_parquet(assignment_artifacts_7day.base_split_assignments, layout.support_7day / "base_split_assignments.parquet", engine=parquet_engine)
    write_parquet(assignment_artifacts_7day.view_split_assignments, layout.support_7day / "view_effective_split_assignments.parquet", engine=parquet_engine)
    write_csv(assignment_artifacts_7day.unsupported_class_audit, layout.support_7day / "unsupported_class_audit.csv")
    v2_coverage = build_v2_coverage_artifacts(
        v2_evidence_3h=weak_sources.v2_temporal_evidence_3h,
        v2_evidence_8h=weak_sources.v2_temporal_evidence_8h,
    )
    write_csv(v2_coverage.daily, layout.v2_coverage / "v2_coverage_daily.csv")
    write_csv(v2_coverage.range_summary, layout.v2_coverage / "v2_coverage_range_summary.csv")
    (layout.v2_coverage / "v2_coverage_report.md").write_text(v2_coverage.markdown_report, encoding="utf-8")

    cohort_artifacts = build_explicit_matched_cohort_artifacts(
        view_assignments=assignment_artifacts_7day.view_split_assignments,
        point_labels=point_labels,
        same_y_labels=v2_same_y,
        record_time_lookup=working.set_index("record.id")["timestamp_local"].to_dict(),
    )
    primary_artifacts = build_primary_protocol_artifacts(
        primary_fold_manifest=fold_quality_7day,
        base_split_assignments=assignment_artifacts_7day.base_split_assignments,
        view_split_assignments=assignment_artifacts_7day.view_split_assignments,
        matched_cohort_manifests=cohort_artifacts.manifests,
        matched_cohort_validation=cohort_artifacts.validation,
    )
    write_csv(primary_artifacts.fold_manifest, layout.primary_folds / "fold_manifest.csv")
    write_parquet(primary_artifacts.base_split_assignments, layout.primary_folds / "base_split_assignments.parquet", engine=parquet_engine)
    write_parquet(primary_artifacts.view_split_assignments, layout.primary_folds / "view_effective_split_assignments.parquet", engine=parquet_engine)
    write_csv(primary_artifacts.matched_cohort_validation, layout.primary_cohorts / "matched_cohort_validation.csv")
    write_csv(primary_artifacts.validation, layout.primary_runner / "runner_assertion_validation.csv")
    write_json_file(layout.primary_runner / "runner_contract.json", primary_artifacts.runner_contract)
    e1_fold_registry = build_e1_fold_registry(
        fold_specs=fold_specs,
        threshold_fit_manifest_hash=threshold_manifest_hash,
        preprocessing_fit_manifest_hash=stable_hash_object(
            {
                "policy": "TRAIN_ONLY_PREPROCESSING_POLICY",
                "fold_ids": [spec.fold_id for spec in fold_specs],
                "maximum_history_horizon": 8,
            }
        ),
    )
    write_csv(e1_fold_registry, layout.domain_manifests / "e1_fold_registry.csv")
    for name, frame in primary_artifacts.matched_cohort_manifests.items():
        write_csv(frame, layout.primary_cohorts / name)
    write_csv(assignment_artifacts_7day.unsupported_class_audit, layout.primary_folds / "unsupported_class_audit.csv")

    protocol_view_assignments_path = layout.primary_folds / "view_effective_split_assignments.parquet"
    task_view_registry = build_task_view_registry(
        native_label_release_dir=config.native_label_release_dir.resolve(),
        dataset_views_run_dir=config.dataset_views_run_dir.resolve(),
        split_artifact_path=protocol_view_assignments_path,
        feature_artifacts=feature_artifacts,
        feature_view_ids=PRIMARY_FEATURE_VIEW_IDS,
    )
    label_frames_by_task = {
        "v0_point_train": point_labels.loc[point_labels["task_id"] == "v0_point_train"].copy(),
        "v1_point_train": point_labels.loc[point_labels["task_id"] == "v1_point_train"].copy(),
        "v2_same_y_3h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_3h"].copy(),
        "v2_same_y_8h": v2_same_y.loc[v2_same_y["task_id"] == "v2_same_y_8h"].copy(),
        "v2_temporal_3h": v2_temporal_3h.copy(),
        "v2_temporal_8h": v2_temporal_8h.copy(),
    }
    label_paths_by_task = {
        "v0_point_train": weak_sources.paths["point_labels_train"],
        "v1_point_train": weak_sources.paths["point_labels_train"],
        "v2_same_y_3h": weak_sources.paths["v2_same_y_labels"],
        "v2_same_y_8h": weak_sources.paths["v2_same_y_labels"],
        "v2_temporal_3h": weak_sources.paths["v2_temporal_labels_3h"],
        "v2_temporal_8h": weak_sources.paths["v2_temporal_labels_8h"],
    }
    label_hashes_by_task = {
        "v0_point_train": weak_sources.hashes["point_labels_train"],
        "v1_point_train": weak_sources.hashes["point_labels_train"],
        "v2_same_y_3h": weak_sources.hashes["v2_same_y_labels"],
        "v2_same_y_8h": weak_sources.hashes["v2_same_y_labels"],
        "v2_temporal_3h": weak_sources.hashes["v2_temporal_labels_3h"],
        "v2_temporal_8h": weak_sources.hashes["v2_temporal_labels_8h"],
    }
    task_training_manifest, task_training_manifest_validation = build_task_training_manifest(
        registry_df=task_view_registry,
        view_assignments=primary_artifacts.view_split_assignments,
        label_frames=label_frames_by_task,
        label_paths=label_paths_by_task,
        label_hashes=label_hashes_by_task,
        protocol_artifact_path=protocol_view_assignments_path,
        protocol_artifact_hash=file_sha256(protocol_view_assignments_path),
        feature_artifacts=feature_artifacts,
        cohort_manifests=primary_artifacts.matched_cohort_manifests,
    )
    comparison_training_manifest, comparison_training_manifest_validation = build_comparison_training_manifest(
        task_training_manifest=task_training_manifest,
        cohort_manifests=primary_artifacts.matched_cohort_manifests,
    )
    frozen_target_manifest, frozen_target_manifest_validation = build_frozen_target_manifest(
        task_training_manifest,
        feature_view_ids=PRIMARY_FEATURE_VIEW_IDS,
    )
    task_training_manifest = extend_manifest_with_contracts(
        task_training_manifest,
        sample_environment_manifest=sample_environment_manifest,
        ontology_id="point_ontology_v1",
    )
    comparison_training_manifest = extend_manifest_with_contracts(
        comparison_training_manifest,
        sample_environment_manifest=sample_environment_manifest,
        ontology_id="point_ontology_v1",
    )
    frozen_target_manifest = extend_manifest_with_contracts(
        frozen_target_manifest,
        sample_environment_manifest=sample_environment_manifest,
        ontology_id="point_ontology_v1",
    )
    representation_artifacts = build_representation_validity_artifacts(
        task_training_manifest=task_training_manifest,
        comparison_training_manifest=comparison_training_manifest,
    )
    estimability_artifacts = build_estimability_artifacts(
        task_training_manifest=task_training_manifest,
        comparison_training_manifest=comparison_training_manifest,
        frozen_target_manifest=frozen_target_manifest,
    )
    write_csv(task_view_registry, layout.primary_runner / "task_view_registry.csv")
    write_parquet(task_training_manifest, layout.primary_runner / "task_training_manifest.parquet", engine=parquet_engine)
    write_csv(task_training_manifest_validation, layout.primary_runner / "task_training_manifest_validation.csv")
    write_parquet(comparison_training_manifest, layout.primary_runner / "comparison_training_manifest.parquet", engine=parquet_engine)
    write_csv(comparison_training_manifest_validation, layout.primary_runner / "comparison_training_manifest_validation.csv")
    write_parquet(frozen_target_manifest, layout.primary_runner / "frozen_target_manifest.parquet", engine=parquet_engine)
    write_csv(frozen_target_manifest_validation, layout.primary_runner / "frozen_target_manifest_validation.csv")
    claim_registry = build_claim_registry(Path(__file__).resolve().parents[4])
    comparison_registry = build_comparison_registry()
    experiment_registry = build_experiment_registry()
    write_yaml_file(layout.run_metadata / "claim_registry.yaml", claim_registry)
    write_csv(comparison_registry, layout.run_metadata / "comparison_registry.csv")
    write_csv(experiment_registry, layout.run_metadata / "experiment_registry.csv")
    discovery_training_manifest = task_training_manifest.loc[
        task_training_manifest["partition"].astype("string").isin(["train", "validation", "test"])
    ].copy()
    temporal_falsification_manifest = task_training_manifest.loc[
        task_training_manifest["environment_id"].astype("string").isin(["E1", "E2"])
    ].copy()
    deployment_transport_manifest = frozen_target_manifest.copy()
    source_expansion_operational_manifest = deployment_transport_manifest.copy()
    source_expansion_operational_manifest["estimand_id"] = "OPERATIONAL_EXPANSION"
    source_expansion_operational_manifest["sampling_strategy_id"] = "FULL_SOURCE_ROWS"
    source_expansion_operational_manifest["sampling_unit"] = "row"
    source_expansion_operational_manifest["budget_value"] = int(len(source_expansion_operational_manifest))
    source_expansion_operational_manifest["budget_tolerance"] = 0
    source_expansion_operational_manifest["number_of_repetitions"] = 1
    source_expansion_operational_manifest["seed_registry_path"] = str((layout.run_metadata / "seed_registry.csv").resolve())
    source_expansion_matched_budget_manifest = deployment_transport_manifest.copy()
    source_expansion_matched_budget_manifest["estimand_id"] = "MATCHED_SEGMENT_DAY_BUDGET_EXPANSION"
    source_expansion_matched_budget_manifest["sampling_strategy_id"] = "MATCHED_SEGMENT_DAY_BUDGET_EXPANSION"
    source_expansion_matched_budget_manifest["sampling_unit"] = "segment_day"
    source_expansion_matched_budget_manifest["budget_value"] = int(
        max(
            1,
            source_expansion_matched_budget_manifest.get("sample_id", pd.Series(dtype="string")).astype("string").nunique(),
        )
    )
    source_expansion_matched_budget_manifest["budget_tolerance"] = 0.05
    source_expansion_matched_budget_manifest["number_of_repetitions"] = 5
    source_expansion_matched_budget_manifest["seed_registry_path"] = str((layout.run_metadata / "seed_registry.csv").resolve())
    seed_registry = pd.DataFrame(
        {
            "repetition_id": [f"rep_{index:02d}" for index in range(1, 6)],
            "random_seed": [41, 42, 43, 44, 45],
        }
    ).convert_dtypes()
    write_csv(seed_registry, layout.run_metadata / "seed_registry.csv")
    write_parquet(discovery_training_manifest, layout.primary_runner / "discovery_training_manifest.parquet", engine=parquet_engine)
    write_parquet(temporal_falsification_manifest, layout.primary_runner / "temporal_falsification_manifest.parquet", engine=parquet_engine)
    write_parquet(source_expansion_operational_manifest, layout.primary_runner / "source_expansion_operational_manifest.parquet", engine=parquet_engine)
    write_parquet(source_expansion_matched_budget_manifest, layout.primary_runner / "source_expansion_matched_budget_manifest.parquet", engine=parquet_engine)
    write_parquet(deployment_transport_manifest, layout.primary_runner / "deployment_transport_manifest.parquet", engine=parquet_engine)
    legacy_to_v2_equivalence_report = build_legacy_to_v2_equivalence_report(
        task_training_manifest=task_training_manifest,
        comparison_training_manifest=comparison_training_manifest,
        frozen_target_manifest=frozen_target_manifest,
        discovery_training_manifest=discovery_training_manifest,
        temporal_falsification_manifest=temporal_falsification_manifest,
        source_expansion_operational_manifest=source_expansion_operational_manifest,
        deployment_transport_manifest=deployment_transport_manifest,
    )
    write_csv(legacy_to_v2_equivalence_report, layout.run_metadata / "legacy_to_v2_equivalence_report.csv")
    runner_contract_v2 = build_runner_contract_v2_payload(
        claim_registry_path=layout.run_metadata / "claim_registry.yaml",
        comparison_registry_path=layout.run_metadata / "comparison_registry.csv",
        experiment_registry_path=layout.run_metadata / "experiment_registry.csv",
        environment_registry_path=layout.domain_manifests / "environment_registry.csv",
    )
    write_json_file(layout.primary_runner / "runner_contract_v2.json", runner_contract_v2)
    write_csv(representation_artifacts.class_specific_retention, layout.validity_representation / "class_specific_retention.csv")
    write_csv(
        representation_artifacts.native_vs_matched_distribution,
        layout.validity_representation / "native_vs_matched_distribution.csv",
    )
    (layout.validity_representation / "representation_validity_report.md").write_text(
        representation_artifacts.markdown_report,
        encoding="utf-8",
    )
    write_csv(estimability_artifacts.matrix, layout.validity_evaluation / "estimability_matrix.csv")

    feature_shift_raw = build_cross_position_feature_shift_raw(working)
    feature_shift_isr = build_cross_position_feature_shift_isr(working)
    label_shift = build_cross_position_label_transport(
        point_labels=point_labels.loc[point_labels["task_id"] == "v0_point_train"].copy(),
        v2_temporal_3h=v2_temporal_3h,
        v2_temporal_8h=v2_temporal_8h,
        frozen_low_threshold=float(threshold_manifest["threshold_value"]),
    )
    write_csv(feature_shift_raw, layout.transport_feature_shift / "cross_position_feature_shift_raw.csv")
    write_csv(feature_shift_isr, layout.transport_feature_shift / "cross_position_feature_shift_isr.csv")
    write_csv(label_shift, layout.transport_label_shift / "cross_position_label_transport.csv")

    q_values = {
        "q10": float(sensitivity_df.loc[0, "q10"]),
    }
    threshold_artifacts = build_threshold_sensitivity_transport(
        label_frames={
            "v0_point_train": point_labels.loc[point_labels["task_id"] == "v0_point_train"].copy(),
            "v2_temporal_3h": v2_temporal_3h.copy(),
            "v2_temporal_8h": v2_temporal_8h.copy(),
        },
        view_assignments=assignment_artifacts_5day.view_split_assignments,
        q_values=q_values,
    )
    write_csv(threshold_artifacts.summary, layout.threshold_transport / "threshold_sensitivity_transport.csv")
    write_csv(threshold_artifacts.distributions, layout.threshold_transport / "threshold_sensitivity_distributions.csv")

    dependency_artifacts = build_dependency_artifacts()
    write_csv(dependency_artifacts.registry, layout.dependency_manifests / "label_dependency_registry_field_level.csv")
    write_csv(dependency_artifacts.proxy_rich, layout.dependency_manifests / "proxy_rich_features.csv")
    write_csv(dependency_artifacts.proxy_reduced, layout.dependency_manifests / "proxy_reduced_features.csv")

    primary_fold_summary = (
        fold_quality_7day.groupby("fold_id", dropna=False, sort=False)["primary_benchmark_eligible"].all().to_dict()
        if not fold_quality_7day.empty
        else {}
    )
    stress_fold_summary = (
        fold_quality_5day.groupby("fold_id", dropna=False, sort=False)["stress_analysis_eligible"].all().to_dict()
        if not fold_quality_5day.empty
        else {}
    )
    validation_report = {
        "protocol_name": "P1_SOURCE__P2_TARGET_PRIMARY_7DAY",
        "protocol_version": "2026-07-16.eval-protocol.v2",
        "p2_has_train_assignment": False,
        "p2_has_validation_assignment": False,
        "primary_protocol": {
            "block_days": 7,
            "selected_fold_ids": ["fold_01"],
            "all_fold_statuses_7day": primary_fold_summary,
            "stress_eligible_folds_5day": [fold_id for fold_id, eligible in stress_fold_summary.items() if eligible],
            "artifact_dir": str(layout.primary_protocol),
            "runner_contract_path": str(layout.primary_runner / "runner_contract.json"),
            "runner_assertion_validation_path": str(layout.primary_runner / "runner_assertion_validation.csv"),
            "task_view_registry_path": str(layout.primary_runner / "task_view_registry.csv"),
            "task_training_manifest_path": str(layout.primary_runner / "task_training_manifest.parquet"),
            "comparison_training_manifest_path": str(layout.primary_runner / "comparison_training_manifest.parquet"),
            "frozen_target_manifest_path": str(layout.primary_runner / "frozen_target_manifest.parquet"),
        },
        "diagnostic_protocol_5day": {
            "fold_count_5day": int(len(fold_specs_5day)),
            "fold_ids_5day": [spec.fold_id for spec in fold_specs_5day],
            "diagnostic_eligible_statuses_5day": {
                str(fold_id): bool(value)
                for fold_id, value in stress_fold_summary.items()
            },
            "artifact_dir": str(layout.support_5day),
        },
        "primary_threshold_policy": "FROZEN_INITIAL_SOURCE",
        "primary_threshold_value_q10": float(threshold_manifest["threshold_value"]),
        "tranche0_contracts": {
            "claim_registry_path": str((layout.run_metadata / "claim_registry.yaml").resolve()),
            "comparison_registry_path": str((layout.run_metadata / "comparison_registry.csv").resolve()),
            "experiment_registry_path": str((layout.run_metadata / "experiment_registry.csv").resolve()),
            "environment_registry_path": str((layout.domain_manifests / "environment_registry.csv").resolve()),
            "sample_environment_manifest_path": str((layout.domain_manifests / "sample_environment_manifest.parquet").resolve()),
            "e1_fold_registry_path": str((layout.domain_manifests / "e1_fold_registry.csv").resolve()),
            "runner_contract_v2_path": str((layout.primary_runner / "runner_contract_v2.json").resolve()),
            "legacy_to_v2_equivalence_report_path": str((layout.run_metadata / "legacy_to_v2_equivalence_report.csv").resolve()),
        },
        "sensitivity_quantiles_reported": ["q10"],
        "threshold_sensitivity_distribution_path": str(layout.threshold_transport / "threshold_sensitivity_distributions.csv"),
        "p2_interpretation_note": "Absence of normal labels in P2 does not prove agronomic normal conditions are absent there.",
        "v2_coverage_diagnostics": {
            "coverage_report_path": str(layout.v2_coverage / "v2_coverage_report.md"),
            "coverage_daily_path": str(layout.v2_coverage / "v2_coverage_daily.csv"),
            "coverage_range_summary_path": str(layout.v2_coverage / "v2_coverage_range_summary.csv"),
        },
        "phase1_validity_diagnostics": {
            "representation_report_path": str(layout.validity_representation / "representation_validity_report.md"),
            "class_specific_retention_path": str(layout.validity_representation / "class_specific_retention.csv"),
            "native_vs_matched_distribution_path": str(layout.validity_representation / "native_vs_matched_distribution.csv"),
            "estimability_matrix_path": str(layout.validity_evaluation / "estimability_matrix.csv"),
        },
        "validation_gates": {
            "matched_cohort_manifests_generated": True,
            "primary_protocol_locked_to_7day_fold_01": True,
            "runner_contract_generated": True,
            "runner_assertions_passed": True,
            "task_view_registry_generated": True,
            "task_training_manifest_generated": True,
            "comparison_training_manifest_generated": True,
            "frozen_target_manifest_generated": True,
            "raw_vs_isr_shift_separated": True,
            "threshold_sensitivity_generated": True,
            "v2_coverage_diagnostic_generated": True,
            "representation_validity_generated": True,
            "estimability_matrix_generated": True,
            "proxy_reduced_validated": bool(dependency_artifacts.validation["proxy_reduced_validated"]),
            "tranche0_v2_contract_generated": True,
            "legacy_to_v2_equivalence_generated": True,
            "smoke_test_executed": False,
            "ready_for_smoke_test": False,
            "full_runner_executed": False,
            "ready_for_full_benchmark": False,
            "remaining_blockers": [
                "downstream benchmark runners still need to execute the frozen_target_manifest final source-to-P2 contract",
            ],
        },
        "training_deferred": True,
        "model_outputs_present": False,
        "native_label_release_dir": str(config.native_label_release_dir),
    }
    write_json_file(layout.run_metadata / "protocol_validation_report.json", validation_report)

    run_manifest = {
        "pipeline": "evaluation_protocols",
        "version": "2026-07-16.eval-protocol.v2",
        "config": _config_to_dict(config),
        "protocol_registry": {
            "run_dir": str(protocol_registry.run_dir),
            "registry_contract_hash": protocol_registry.run_manifest["registry_contract_hash"],
            "protocol_stage_id": config.protocol_stage_id,
            "authority_mode": "UPSTREAM_PROTOCOL_REGISTRY",
        },
        "input_hashes": {
            "canonical_history": str(config.canonical_history_path.resolve()),
            "feature_catalog": str(config.feature_catalog_path.resolve()),
            "segment_manifest": str(segment_manifest_path.resolve()),
            "linked_dataset_views_run_dir": str(config.dataset_views_run_dir.resolve()),
            "dataset_views_run_hash": _optional_manifest_hash(config.dataset_views_run_dir),
            "linked_native_label_release_dir": str(config.native_label_release_dir.resolve()),
            "native_label_release_hash": file_sha256(
                config.native_label_release_dir.resolve() / "run_metadata" / "label_release_manifest.json"
            ),
        },
        "linked_dataset_view_outputs": sorted(
            str(path.relative_to(config.dataset_views_run_dir))
            for path in config.dataset_views_run_dir.rglob("*")
            if path.is_file()
        ),
        "linked_native_label_outputs": sorted(str(path.relative_to(config.native_label_release_dir)) for path in config.native_label_release_dir.rglob("*") if path.is_file()),
        "training_deferred": True,
        "artifact_layout_version": "evaluation_protocols.layout.v2",
        "primary_protocol_dir": str(layout.primary_protocol),
        "diagnostic_7day_dir": str(layout.support_7day),
        "tranche0_v2_outputs": {
            "environment_registry_path": str((layout.domain_manifests / "environment_registry.csv").resolve()),
            "sample_environment_manifest_path": str((layout.domain_manifests / "sample_environment_manifest.parquet").resolve()),
            "e1_fold_registry_path": str((layout.domain_manifests / "e1_fold_registry.csv").resolve()),
            "claim_registry_path": str((layout.run_metadata / "claim_registry.yaml").resolve()),
            "comparison_registry_path": str((layout.run_metadata / "comparison_registry.csv").resolve()),
            "experiment_registry_path": str((layout.run_metadata / "experiment_registry.csv").resolve()),
            "discovery_training_manifest_path": str((layout.primary_runner / "discovery_training_manifest.parquet").resolve()),
            "temporal_falsification_manifest_path": str((layout.primary_runner / "temporal_falsification_manifest.parquet").resolve()),
            "source_expansion_operational_manifest_path": str((layout.primary_runner / "source_expansion_operational_manifest.parquet").resolve()),
            "source_expansion_matched_budget_manifest_path": str((layout.primary_runner / "source_expansion_matched_budget_manifest.parquet").resolve()),
            "deployment_transport_manifest_path": str((layout.primary_runner / "deployment_transport_manifest.parquet").resolve()),
            "runner_contract_v2_path": str((layout.primary_runner / "runner_contract_v2.json").resolve()),
            "legacy_to_v2_equivalence_report_path": str((layout.run_metadata / "legacy_to_v2_equivalence_report.csv").resolve()),
        },
    }
    write_json_file(layout.run_metadata / "run_manifest.json", run_manifest)
    write_artifact_guides(layout)
    write_csv(pd.DataFrame(build_artifact_catalog(layout)).convert_dtypes(), layout.run_metadata / "artifact_catalog.csv")
    return EvaluationProtocolResult(
        run_id=run_id,
        output_dir=output_dir,
        source_row_count=int(len(p1_df)),
        target_row_count=int(len(p2_df)),
    )


def _config_to_dict(config: EvaluationProtocolConfig) -> dict[str, object]:
    return {
        "protocol_registry_run_dir": str(config.protocol_registry_run_dir),
        "protocol_stage_id": config.protocol_stage_id,
        "canonical_history_path": str(config.canonical_history_path),
        "feature_catalog_path": str(config.feature_catalog_path),
        "manifest_path": str(config.manifest_path),
        "segment_manifest_path": str(config.segment_manifest_path) if config.segment_manifest_path is not None else None,
        "dataset_views_run_dir": str(config.dataset_views_run_dir),
        "native_label_release_dir": str(config.native_label_release_dir),
        "output_root": str(config.output_root),
        "rolling_block_days": config.rolling_block_days,
        "initial_train_blocks": config.initial_train_blocks,
        "validation_blocks": config.validation_blocks,
        "test_blocks": config.test_blocks,
        "compare_block_days": list(config.compare_block_days),
        "p2_warm_start_enabled": config.p2_warm_start_enabled,
        "warmup_duration_hours": config.warmup_duration_hours,
    }


def _optional_manifest_hash(run_dir: Path) -> str | None:
    manifest = run_dir.resolve() / "run_metadata" / "run_manifest.json"
    return file_sha256(manifest) if manifest.exists() else None


def _validate_protocol_registry_authority(config: EvaluationProtocolConfig, registry) -> None:
    if bool(registry.run_manifest.get("phase_a_only", False)):
        raise PermissionError(
            "This protocol registry is Phase A audit-only. "
            "STOP before evaluation_protocols until a Phase B frozen registry exists."
        )
    if not bool(registry.run_manifest.get("evaluation_protocols_unlocked", False)):
        raise PermissionError(
            "Protocol registry has not unlocked evaluation_protocols. "
            "The native label release must be completed before evaluation."
        )
    if not bool(registry.run_manifest.get("semantic_contract_frozen", False)):
        raise PermissionError("Evaluation requires a frozen Phase B semantic contract.")
    if not bool(registry.run_manifest.get("native_engine_implemented", False)):
        raise PermissionError("Evaluation remains locked until the Phase C native engine is implemented.")
    if str(registry.run_manifest.get("canonical_manifest_hash")) != file_sha256(config.manifest_path.resolve()):
        raise ValueError("Protocol registry canonical-manifest hash does not match evaluation input.")
    required = (
        ("E1", "inspect_sensitive"),
        ("E2", "inspect_sensitive"),
        ("E3_TARGET_PREEXPOSED", "evaluate"),
    )
    denied = [
        f"{environment_id}:{operation}"
        for environment_id, operation in required
        if not authorize_operation(registry, config.protocol_stage_id, environment_id, operation).allowed
    ]
    if denied:
        raise PermissionError(
            "Governed evaluation protocol is not authorized at "
            f"{config.protocol_stage_id}: {', '.join(denied)}"
        )
