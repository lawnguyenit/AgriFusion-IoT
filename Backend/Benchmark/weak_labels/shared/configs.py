from __future__ import annotations

WEAK_LABELS_PIPELINE_NAME = "weak_labels"
WEAK_LABELS_VERSION = "2026-07-16.v1"
WEAK_LABELS_DEFAULT_RUN_PROFILE = "chronological_temporal"

POINT_TASK_IDS: tuple[str, ...] = ("v0_point_train", "v1_point_train")
V2_SAME_Y_TASK_IDS: tuple[str, ...] = ("v2_same_y_3h", "v2_same_y_8h")
V2_TEMPORAL_TASK_IDS: tuple[str, ...] = ("v2_temporal_3h", "v2_temporal_8h")

CURRENT_PRIMARY_SCOPE_TASK_IDS: tuple[str, ...] = (
    "v0_point_train",
    "v1_point_train",
    "v2_same_y_3h",
    "v2_temporal_3h",
)

OPTIONAL_EXPLICIT_TASK_IDS: tuple[str, ...] = (
    "v2_same_y_8h",
    "v2_temporal_8h",
)

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
DEFAULT_PERSISTENT_LOW_RUN_MIN_STEPS = 3
THERMAL_EVIDENCE_THRESHOLD_KPA = 2.5
MOISTURE_RISE_DELTA_PP = 5.0

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

PRIMARY_OUTPUT_FILES: tuple[str, ...] = (
    "point/point_evidence_flags.parquet",
    "point/point_labels_detailed.parquet",
    "point/point_labels_train.parquet",
    "point/technical_labels_audit.parquet",
    "v2/v2_same_y_labels.parquet",
    "v2/v2_temporal_evidence_3h.parquet",
    "v2/v2_temporal_evidence_8h.parquet",
    "v2/v2_temporal_labels_3h.parquet",
    "v2/v2_temporal_labels_8h.parquet",
    "v2/matched_cohort_manifest.parquet",
    "v2/v2_label_agreement_3h_8h.csv",
    "registries/label_registry.yaml",
    "registries/label_dependency_registry.csv",
    "audits/label_distribution.csv",
    "audits/label_overlap_matrix.csv",
    "audits/excluded_samples_audit.csv",
    "audits/label_examples.csv",
    "audit/label_assignment.parquet",
    "audit/rule_firings.parquet",
    "audit/rule_registry.csv",
    "audit/threshold_registry.csv",
    "audit/label_source_dependency.csv",
    "threshold_diagnostics/threshold_sensitivity.csv",
    "threshold_diagnostics/persistent_low_k_support.csv",
    "run_metadata/run_manifest.json",
    "run_metadata/artifact_catalog.csv",
    "run_metadata/current_scope_summary.json",
    "ARTIFACT_GUIDE.md",
)
