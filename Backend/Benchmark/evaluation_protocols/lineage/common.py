from __future__ import annotations

import pandas as pd


EXPECTED_LABELS_BY_VIEW: dict[str, tuple[str, ...]] = {
    "v0_point_train": (
        "normal_point",
        "low_relative_moisture_point",
        "unknown_environment_point",
    ),
    "v1_point_train": (
        "normal_point",
        "low_relative_moisture_point",
        "unknown_environment_point",
    ),
    "v2_same_y_3h": (
        "normal_point",
        "low_relative_moisture_point",
        "unknown_environment_point",
    ),
    "v2_same_y_8h": (
        "normal_point",
        "low_relative_moisture_point",
        "unknown_environment_point",
    ),
    "v2_temporal_3h": (
        "normal_window_context",
        "persistent_low_relative_moisture_window",
        "unknown_environment_window",
    ),
    "v2_temporal_8h": (
        "normal_window_context",
        "persistent_low_relative_moisture_window",
        "unknown_environment_window",
    ),
    "v6_event": (
        "normal",
        "persistent_low_relative_moisture_event",
        "unknown_environment_event",
    ),
    "v6_b8_block": (
        "normal_block",
        "persistent_low_relative_moisture_block",
        "unknown_or_mixed_environment_block",
    ),
}


def attach_event_domains(event_df: pd.DataFrame, domain_by_segment: dict[str, str]) -> pd.DataFrame:
    result = event_df.copy()
    result["deployment_domain_name"] = (
        result["record.segment_id"].astype("string").map(domain_by_segment).fillna("UNKNOWN").astype("string")
    )
    return result.convert_dtypes()


def attach_block_domains(
    block_labels: pd.DataFrame,
    block_composition: pd.DataFrame,
    domain_by_segment: dict[str, str],
) -> pd.DataFrame:
    metadata = block_composition.loc[
        :,
        ["sample_id", "record.segment_id", "block_day_key", "block_window_label"],
    ].copy()
    metadata["deployment_domain_name"] = (
        metadata["record.segment_id"].astype("string").map(domain_by_segment).fillna("UNKNOWN").astype("string")
    )
    metadata["block_start_local"] = metadata.apply(resolve_block_start_timestamp, axis=1).astype(
        "datetime64[ns, Asia/Ho_Chi_Minh]"
    )
    result = block_labels.merge(metadata, on="sample_id", how="left", validate="one_to_one")
    return result.convert_dtypes()


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


def resolve_block_start_timestamp(row: pd.Series) -> pd.Timestamp:
    day = str(row["block_day_key"])
    bucket = str(row["block_window_label"])
    hour = {"00-08": 0, "08-16": 8, "16-24": 16}.get(bucket, 0)
    return pd.Timestamp(f"{day} {hour:02d}:00:00", tz="Asia/Ho_Chi_Minh")
