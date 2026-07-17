from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class WeakLabelsConfig:
    canonical_history_path: Path
    feature_catalog_path: Path
    output_root: Path
    manifest_path: Path | None = None
    segment_manifest_path: Path | None = None
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    base_split_strategy: str = "chronological_v1"
    run_profile: str = "chronological_temporal"
    threshold_mode: str = "TRAIN_FITTED_GLOBAL"
    split_gap_minutes_override: int | None = None
    random_seed: int = 42


@dataclass(frozen=True)
class WeakLabelsResult:
    run_id: str
    output_dir: Path
    row_count: int
    generated_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThresholdRecord:
    threshold_id: str
    threshold_version: str
    fit_mode: str
    source_fields: tuple[str, ...]
    fit_partition: str
    fit_record_count: int
    fit_record_hash: str
    segment_scope: str
    value: float
    notes: str = ""


@dataclass
class LabelArtifactBundle:
    point_evidence_flags: object
    point_labels_detailed: object
    point_labels_train: object
    technical_labels_audit: object
    v2_same_y_labels: object
    v2_temporal_evidence_3h: object
    v2_temporal_evidence_8h: object
    v2_temporal_labels_3h: object
    v2_temporal_labels_8h: object
    v6_event_labels: object
    v6_b8_block_composition: object
    v6_b8_block_labels: object
    matched_cohort_manifest: object
    boundary_event_audit: object
    label_dependency_registry: object
    label_distribution: object
    label_overlap_matrix: object
    threshold_sensitivity: object
    excluded_samples_audit: object
    label_examples: object
    v2_label_agreement_3h_8h: object
    run_manifest: dict[str, object]
    label_registry: dict[str, object]
    additional_payloads: dict[str, object] = field(default_factory=dict)
