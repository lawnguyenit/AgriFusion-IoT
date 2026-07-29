from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class EnvironmentSpec:
    environment_id: str
    stage_name: str
    start_local: pd.Timestamp
    end_local: pd.Timestamp
    deployment_id: str
    boundary_status: str
    boundary_reason: str
    train_description: str
    evaluation_description: str
    stage_question: str


@dataclass(frozen=True)
class ValidityLifecycleConfig:
    evaluation_protocol_run_dir: Path
    output_root: Path
    environment_specs: tuple[EnvironmentSpec, ...]
    model_suite_run_dir: Path | None = None
    support_min_samples: int = 5
    support_min_days: int = 2
    support_min_segments: int = 1
    low_eligibility_rate_threshold: float = 0.25


@dataclass(frozen=True)
class ProtocolLifecycleInputs:
    evaluation_protocol_run_dir: Path
    dataset_views_run_dir: Path
    weak_labels_run_dir: Path
    canonical_history_path: Path
    feature_catalog_path: Path
    segment_manifest_path: Path
    deployment_domains: pd.DataFrame
    canonical_df: pd.DataFrame
    task_training_manifest: pd.DataFrame
    comparison_training_manifest: pd.DataFrame
    frozen_target_manifest: pd.DataFrame
    task_view_registry: pd.DataFrame
    point_labels_train: pd.DataFrame
    point_labels_detailed: pd.DataFrame
    point_evidence_flags: pd.DataFrame
    v2_same_y_labels: pd.DataFrame
    v2_temporal_evidence_3h: pd.DataFrame
    v2_temporal_evidence_8h: pd.DataFrame
    v2_temporal_labels_3h: pd.DataFrame
    v2_temporal_labels_8h: pd.DataFrame
    dataset_metadata: pd.DataFrame
    dataset_row_index: pd.DataFrame
    v1_features: pd.DataFrame
    v2_window_quality_3h: pd.DataFrame
    v2_window_quality_8h: pd.DataFrame
    run_manifest: dict[str, object]
    protocol_validation_report: dict[str, object]


@dataclass(frozen=True)
class ValidityLifecycleResult:
    run_id: str
    output_dir: Path
    overall_status: str
    observation_count: int
