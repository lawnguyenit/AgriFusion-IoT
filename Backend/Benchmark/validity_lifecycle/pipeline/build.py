from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.validators import ensure_parquet_engine
from Backend.Benchmark.shared.artifacts import create_run_directory, write_yaml
from Backend.Benchmark.validity_lifecycle.audits import (
    build_class_day_segment_support,
    build_comparison_hash_audit,
    build_ec_npk_dependency_audit,
    build_environment_continuity_matrix,
    build_environment_eligibility_matrix,
    build_environment_support_matrix,
    build_label_first_occurrence_audit,
    build_ph_measurement_stability_audit,
)
from Backend.Benchmark.validity_lifecycle.contracts import ValidityLifecycleConfig, ValidityLifecycleResult
from Backend.Benchmark.validity_lifecycle.defaults import EXPECTED_POINT_TARGETS, config_file_payloads
from Backend.Benchmark.validity_lifecycle.layout import build_artifact_catalog, build_validity_lifecycle_layout
from Backend.Benchmark.validity_lifecycle.loaders import load_protocol_lifecycle_inputs
from Backend.Benchmark.validity_lifecycle.registry import build_observation_artifacts
from Backend.Benchmark.validity_lifecycle.reporting import build_validation_payload, render_validity_lifecycle_report
from Backend.Benchmark.weak_labels.io import write_csv, write_json_file, write_parquet


def build_validity_lifecycle(config: ValidityLifecycleConfig) -> ValidityLifecycleResult:
    parquet_engine = ensure_parquet_engine()
    inputs = load_protocol_lifecycle_inputs(config.evaluation_protocol_run_dir)
    run_id, output_dir = create_run_directory(config.output_root.resolve(), prefix="validity_lifecycle")
    layout = build_validity_lifecycle_layout(output_dir)
    layout.create()

    for relative_path, payload in config_file_payloads().items():
        write_yaml(layout.configs / relative_path, payload)

    observation_artifacts = build_observation_artifacts(inputs=inputs, environment_specs=config.environment_specs)
    support_df = build_environment_support_matrix(
        observation_artifacts.view_observation_registry,
        environment_specs=config.environment_specs,
        expected_targets=EXPECTED_POINT_TARGETS,
        min_samples=config.support_min_samples,
        min_days=config.support_min_days,
        min_segments=config.support_min_segments,
    )
    eligibility_df = build_environment_eligibility_matrix(observation_artifacts.view_observation_registry)
    continuity_df = build_environment_continuity_matrix(observation_artifacts.observation_registry)
    label_first_occurrence_df = build_label_first_occurrence_audit(
        observation_artifacts.view_observation_registry,
        config.environment_specs,
        expected_targets=EXPECTED_POINT_TARGETS,
    )
    class_day_segment_df = build_class_day_segment_support(
        observation_artifacts.view_observation_registry,
        config.environment_specs,
        expected_targets=EXPECTED_POINT_TARGETS,
    )
    comparison_hash_df = build_comparison_hash_audit(
        inputs.comparison_training_manifest,
        observation_artifacts.observation_registry,
    )
    ec_dependency_df = build_ec_npk_dependency_audit(observation_artifacts.observation_registry)
    ph_stability_df = build_ph_measurement_stability_audit(observation_artifacts.observation_registry)
    validation_payload = build_validation_payload(
        config=config,
        support_df=support_df,
        eligibility_df=eligibility_df,
        comparison_hash_df=comparison_hash_df,
        ec_dependency_df=ec_dependency_df,
        ph_stability_df=ph_stability_df,
    )
    report_markdown = render_validity_lifecycle_report(
        validation_payload=validation_payload,
        config=config,
        support_df=support_df,
        eligibility_df=eligibility_df,
        comparison_hash_df=comparison_hash_df,
        ec_dependency_df=ec_dependency_df,
        ph_stability_df=ph_stability_df,
    )

    write_parquet(observation_artifacts.observation_registry, layout.manifests / "observation_registry.parquet", engine=parquet_engine)
    write_csv(observation_artifacts.observation_registry, layout.manifests / "observation_registry.csv")
    write_parquet(observation_artifacts.view_observation_registry, layout.manifests / "view_observation_registry.parquet", engine=parquet_engine)
    write_csv(observation_artifacts.view_observation_registry, layout.manifests / "view_observation_registry.csv")
    write_csv(support_df, layout.audits / "environment_support_matrix.csv")
    write_csv(eligibility_df, layout.audits / "environment_eligibility_matrix.csv")
    write_csv(continuity_df, layout.audits / "environment_continuity_matrix.csv")
    write_csv(label_first_occurrence_df, layout.audits / "label_first_occurrence.csv")
    write_csv(class_day_segment_df, layout.audits / "class_day_segment_support.csv")
    write_csv(comparison_hash_df, layout.audits / "comparison_hash_audit.csv")
    write_csv(ec_dependency_df, layout.audits / "ec_npk_dependency.csv")
    write_csv(ph_stability_df, layout.audits / "ph_measurement_stability.csv")
    (layout.reports / "validity_lifecycle_audit_report.md").write_text(report_markdown, encoding="utf-8")

    lifecycle_validation = {
        **validation_payload,
        "input_protocol_run_dir": str(config.evaluation_protocol_run_dir.resolve()),
        "output_dir": str(output_dir),
    }
    write_json_file(layout.run_metadata / "validity_lifecycle_validation.json", lifecycle_validation)
    write_json_file(
        layout.run_metadata / "run_manifest.json",
        {
            "pipeline": "validity_lifecycle",
            "version": "2026-07-26.validity-lifecycle.v1",
            "evaluation_protocol_run_dir": str(config.evaluation_protocol_run_dir.resolve()),
            "linked_dataset_views_run_dir": str(inputs.dataset_views_run_dir),
            "linked_weak_labels_run_dir": str(inputs.weak_labels_run_dir),
            "linked_canonical_history_path": str(inputs.canonical_history_path),
            "environment_ids": [spec.environment_id for spec in config.environment_specs],
            "overall_status": validation_payload["overall_status"],
        },
    )
    write_csv(pd.DataFrame(build_artifact_catalog(layout)).convert_dtypes(), layout.run_metadata / "artifact_catalog.csv")
    return ValidityLifecycleResult(
        run_id=run_id,
        output_dir=output_dir,
        overall_status=str(validation_payload["overall_status"]),
        observation_count=int(len(observation_artifacts.observation_registry)),
    )
