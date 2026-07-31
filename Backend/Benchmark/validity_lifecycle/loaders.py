from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.paths import EVALUATION_PROTOCOLS_ROOT
from Backend.Benchmark.evaluation_protocols.pipeline.consumption import load_native_label_sources
from Backend.Benchmark.validity_lifecycle.contracts import ProtocolLifecycleInputs
from Backend.Benchmark.weak_labels.infrastructure.io import load_canonical_history


def resolve_latest_evaluation_protocol_run() -> Path:
    artifacts_root = EVALUATION_PROTOCOLS_ROOT / "artifacts"
    candidates = [path for path in artifacts_root.iterdir() if path.is_dir()] if artifacts_root.exists() else []
    if not candidates:
        raise FileNotFoundError("No evaluation_protocols artifact runs were found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_protocol_lifecycle_inputs(evaluation_protocol_run_dir: Path) -> ProtocolLifecycleInputs:
    run_dir = evaluation_protocol_run_dir.resolve()
    run_manifest = _load_json_file(run_dir / "run_metadata" / "run_manifest.json")
    protocol_validation_report = _load_json_file(run_dir / "run_metadata" / "protocol_validation_report.json")
    config = run_manifest["config"]
    dataset_views_run_dir = Path(str(config["dataset_views_run_dir"])).resolve()
    native_label_release_dir = Path(str(config["native_label_release_dir"])).resolve()
    canonical_history_path = Path(str(config["canonical_history_path"])).resolve()
    feature_catalog_path = Path(str(config["feature_catalog_path"])).resolve()
    segment_manifest_path = Path(str(run_manifest["input_hashes"]["segment_manifest"])).resolve()

    native_sources = load_native_label_sources(native_label_release_dir)
    canonical_df = load_canonical_history(canonical_history_path).convert_dtypes()
    dataset_metadata = pd.read_parquet(dataset_views_run_dir / "shared" / "metadata.parquet").convert_dtypes()
    dataset_row_index = pd.read_parquet(dataset_views_run_dir / "shared" / "row_index.parquet").convert_dtypes()
    v1_features = pd.read_parquet(dataset_views_run_dir / "views" / "v1_sensor_row" / "X.parquet").convert_dtypes()
    v2_window_quality_3h = pd.read_parquet(dataset_views_run_dir / "views" / "v2_sensor_row_window_3h" / "window_quality_audit.parquet").convert_dtypes()
    v2_window_quality_8h = pd.read_parquet(dataset_views_run_dir / "views" / "v2_sensor_row_window_8h" / "window_quality_audit.parquet").convert_dtypes()
    deployment_domains = pd.read_csv(run_dir / "domain_manifests" / "deployment_domains.csv").convert_dtypes()
    task_training_manifest = pd.read_parquet(run_dir / "primary_protocol" / "runner" / "task_training_manifest.parquet").convert_dtypes()
    comparison_training_manifest = pd.read_parquet(run_dir / "primary_protocol" / "runner" / "comparison_training_manifest.parquet").convert_dtypes()
    frozen_target_manifest = pd.read_parquet(run_dir / "primary_protocol" / "runner" / "frozen_target_manifest.parquet").convert_dtypes()
    task_view_registry = pd.read_csv(run_dir / "primary_protocol" / "runner" / "task_view_registry.csv").convert_dtypes()

    return ProtocolLifecycleInputs(
        evaluation_protocol_run_dir=run_dir,
        dataset_views_run_dir=dataset_views_run_dir,
        native_label_release_dir=native_label_release_dir,
        canonical_history_path=canonical_history_path,
        feature_catalog_path=feature_catalog_path,
        segment_manifest_path=segment_manifest_path,
        deployment_domains=deployment_domains,
        canonical_df=canonical_df,
        task_training_manifest=task_training_manifest,
        comparison_training_manifest=comparison_training_manifest,
        frozen_target_manifest=frozen_target_manifest,
        task_view_registry=task_view_registry,
        point_labels_train=native_sources.point_labels_train,
        point_labels_detailed=native_sources.point_labels_detailed,
        point_evidence_flags=native_sources.point_evidence_flags,
        v2_same_y_labels=native_sources.v2_same_y_labels,
        v2_temporal_evidence_3h=native_sources.v2_temporal_evidence_3h,
        v2_temporal_evidence_8h=native_sources.v2_temporal_evidence_8h,
        v2_temporal_labels_3h=native_sources.v2_temporal_labels_3h,
        v2_temporal_labels_8h=native_sources.v2_temporal_labels_8h,
        dataset_metadata=dataset_metadata,
        dataset_row_index=dataset_row_index,
        v1_features=v1_features,
        v2_window_quality_3h=v2_window_quality_3h,
        v2_window_quality_8h=v2_window_quality_8h,
        run_manifest=run_manifest,
        protocol_validation_report=protocol_validation_report,
    )


def _load_json_file(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
