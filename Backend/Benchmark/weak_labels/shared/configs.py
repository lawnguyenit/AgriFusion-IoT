from __future__ import annotations

from Backend.Benchmark.dataset_views.configs.environmental_events import (
    V6_CHUNK_HOURS,
    V6_CHUNK_START_HOURS,
    V6_LOW_MOISTURE_ONSET_MIN_STEPS,
    V6_MIN_CHUNK_COVERAGE_RATIO,
    V6_RAPID_WETTING_DELTA_PP,
    V6_THERMAL_VPD_THRESHOLD_KPA,
)


WEAK_LABELS_PIPELINE_NAME = "weak_labels"
WEAK_LABELS_VERSION = "2026-07-16.v1"
WEAK_LABELS_DEFAULT_RUN_PROFILE = "chronological_temporal"

POINT_TASK_IDS: tuple[str, ...] = ("v0_point_train", "v1_point_train")
V2_SAME_Y_TASK_IDS: tuple[str, ...] = ("v2_same_y_3h", "v2_same_y_8h")
V2_TEMPORAL_TASK_IDS: tuple[str, ...] = ("v2_temporal_3h", "v2_temporal_8h")
V6_EVENT_TASK_ID = "v6_event"
V6_BLOCK_TASK_ID = "v6_b8_block"

POINT_LABELS: tuple[str, ...] = (
    "normal_point",
    "low_relative_moisture_point",
    "unknown_environment_point",
)
POINT_SENSITIVITY_LABEL = "moisture_rise_transition_point"

V2_TEMPORAL_LABELS: tuple[str, ...] = (
    "normal_window_context",
    "persistent_low_relative_moisture_window",
    "unknown_environment_window",
)
V2_TEMPORAL_EXCLUDED_LABEL = "insufficient_window_context"

V6_EVENT_LABELS: tuple[str, ...] = (
    "normal",
    "persistent_low_relative_moisture_event",
    "unknown_environment_event",
)

V6_BLOCK_LABELS: tuple[str, ...] = (
    "normal_block",
    "persistent_low_relative_moisture_block",
    "unknown_or_mixed_environment_block",
)
V6_BLOCK_EXCLUDED_LABEL = "insufficient_coverage_block"

LABEL_STATUS_LABELED = "LABELED"
LABEL_STATUS_ABSTAIN = "ABSTAIN_INSUFFICIENT_EVIDENCE"
LABEL_STATUS_EXCLUDED_TIME = "EXCLUDED_TIME_INTEGRITY"
LABEL_STATUS_EXCLUDED_WINDOW = "EXCLUDED_WINDOW_INELIGIBLE"

THRESHOLD_MODE_FIXED_DOMAIN = "FIXED_DOMAIN"
THRESHOLD_MODE_FIXED_REPOSITORY = "FIXED_REPOSITORY"
THRESHOLD_MODE_TRAIN_FITTED_GLOBAL = "TRAIN_FITTED_GLOBAL"
THRESHOLD_MODE_TRAIN_FITTED_SEGMENT = "TRAIN_FITTED_SEGMENT"
THRESHOLD_MODE_REUSED_FROZEN_MANIFEST = "REUSED_FROZEN_MANIFEST"

SUPPORTED_RUN_PROFILES: tuple[str, ...] = (
    "chronological_temporal",
    "segment_holdout_last",
)

DEFAULT_POINT_REQUIRED_EVIDENCE_COLUMNS: tuple[str, ...] = (
    "low_moisture_applicable",
    "thermal_applicable",
    "ec_shift_applicable",
    "moisture_rise_applicable",
)

V6_LOW_RUN_MIN_STEPS = V6_LOW_MOISTURE_ONSET_MIN_STEPS
V6_THERMAL_THRESHOLD_KPA = V6_THERMAL_VPD_THRESHOLD_KPA
V6_RISE_DELTA_PP = V6_RAPID_WETTING_DELTA_PP
V6_BLOCK_HOURS = V6_CHUNK_HOURS
V6_BLOCK_START_HOURS = V6_CHUNK_START_HOURS
V6_BLOCK_MIN_COVERAGE_RATIO = V6_MIN_CHUNK_COVERAGE_RATIO

PRIMARY_OUTPUT_FILES: tuple[str, ...] = (
    "point_evidence_flags.parquet",
    "point_labels_detailed.parquet",
    "point_labels_train.parquet",
    "technical_labels_audit.parquet",
    "v2_same_y_labels.parquet",
    "v2_temporal_evidence_3h.parquet",
    "v2_temporal_evidence_8h.parquet",
    "v2_temporal_labels_3h.parquet",
    "v2_temporal_labels_8h.parquet",
    "v6_event_labels.parquet",
    "v6_b8_block_composition.parquet",
    "v6_b8_block_labels.parquet",
    "base_split_assignments.parquet",
    "view_split_assignments.parquet",
    "matched_cohort_manifest.parquet",
    "boundary_event_audit.parquet",
    "label_registry.yaml",
    "label_dependency_registry.csv",
    "label_distribution.csv",
    "label_overlap_matrix.csv",
    "threshold_sensitivity.csv",
    "excluded_samples_audit.csv",
    "label_examples.csv",
    "run_manifest.json",
    "split_manifest.json",
    "v2_label_agreement_3h_8h.csv",
)
