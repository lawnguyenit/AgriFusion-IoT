from __future__ import annotations

import pandas as pd


EXPECTED_LABELS_BY_VIEW: dict[str, tuple[str, ...]] = {
    "v0_point_train": (
        "reference_context_point",
        "low_relative_moisture_point",
        "unresolved_environmental_evidence_point",
    ),
    "v1_point_train": (
        "reference_context_point",
        "low_relative_moisture_point",
        "unresolved_environmental_evidence_point",
    ),
    "v2_same_y_3h": (
        "reference_context_point",
        "low_relative_moisture_point",
        "unresolved_environmental_evidence_point",
    ),
    "v2_same_y_8h": (
        "reference_context_point",
        "low_relative_moisture_point",
        "unresolved_environmental_evidence_point",
    ),
    "v2_temporal_3h": (
        "reference_context_at_anchor",
        "persistent_low_relative_moisture_at_anchor",
        "unresolved_environmental_evidence_at_anchor",
    ),
    "v2_temporal_8h": (
        "reference_context_at_anchor",
        "persistent_low_relative_moisture_at_anchor",
        "unresolved_environmental_evidence_at_anchor",
    ),
}


def fold_partition(timestamp: pd.Timestamp | None, spec) -> str | None:
    if timestamp is None or pd.isna(timestamp):
        return None
    if spec.train_start <= timestamp < spec.train_end:
        return "train"
    if spec.validation_start <= timestamp < spec.validation_end:
        return "validation"
    if spec.test_start <= timestamp < spec.test_end:
        return "test"
    return None


def resolve_v2_effective_partition_for_fold(
    *,
    base_partition: str,
    timestamp: pd.Timestamp | None,
    spec,
    purge_minutes: int,
    source_intrinsic_eligibility: bool,
    source_label_status: str,
    source_exclusion_reason,
) -> tuple[str, object]:
    if source_label_status != "LABELED" or not bool(source_intrinsic_eligibility):
        return "excluded", source_exclusion_reason
    if timestamp is None or pd.isna(timestamp):
        return "excluded", "missing_timestamp"
    if base_partition == "validation" and timestamp < spec.validation_start + pd.Timedelta(minutes=purge_minutes):
        return "excluded", "purge_boundary"
    if base_partition == "test" and timestamp < spec.test_start + pd.Timedelta(minutes=purge_minutes):
        return "excluded", "purge_boundary"
    return base_partition, pd.NA
