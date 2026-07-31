from __future__ import annotations

import pandas as pd

from Backend.Benchmark.evaluation_protocols.lineage.common import (
    fold_partition,
    resolve_v2_effective_partition_for_fold,
)


def build_p1_base_assignments(p1_records: pd.DataFrame, spec) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in p1_records.itertuples(index=False):
        partition = fold_partition(row.timestamp_local, spec)
        if partition is None:
            continue
        rows.append(
            {
                "record_id": str(row[0]),
                "timestamp_local": pd.Timestamp(row.timestamp_local).isoformat(),
                "fold_id": spec.fold_id,
                "fold_policy_id": getattr(spec, "fold_policy_id", "UNSPECIFIED"),
                "deployment_domain": "P1_SOURCE",
                "base_partition": partition,
                "effective_partition": partition,
            }
        )
    return rows


def build_p2_base_assignments(p2_records: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in p2_records.itertuples(index=False):
        rows.append(
            {
                "record_id": str(row[0]),
                "timestamp_local": pd.Timestamp(row.timestamp_local).isoformat(),
                "fold_id": "p2_target_holdout",
                "deployment_domain": "P2_TARGET",
                "base_partition": "target_test",
                "effective_partition": "target_test",
            }
        )
    return rows


def build_fold_point_assignments(
    point_labels: pd.DataFrame,
    spec,
    record_time: dict[str, pd.Timestamp],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    source_rows = point_labels.loc[point_labels["deployment_domain_name"].astype("string") == "P1_SOURCE"].copy()
    for row in source_rows.itertuples(index=False):
        sample_id = str(row.sample_id)
        partition = fold_partition(record_time.get(sample_id), spec)
        if partition is None:
            continue
        intrinsic_eligible = bool(getattr(row, "intrinsic_eligibility", str(row.label_status) == "LABELED"))
        effective = partition if str(row.label_status) == "LABELED" and intrinsic_eligible else "excluded"
        rows.append(
            {
                "sample_id": sample_id,
                "record_id": sample_id,
                "view_id": str(row.task_id),
                "protocol_view_id": str(row.task_id),
                "fold_id": spec.fold_id,
                "fold_policy_id": getattr(spec, "fold_policy_id", "UNSPECIFIED"),
                "deployment_domain": "P1_SOURCE",
                "base_partition": partition,
                "effective_partition": effective,
                "protocol_eligibility": effective != "excluded",
                "group_id": sample_id,
                "eligibility_status": "eligible" if effective != "excluded" else "excluded",
                "exclusion_reason": (
                    pd.NA
                    if effective != "excluded"
                    else getattr(row, "intrinsic_exclusion_reason", pd.NA)
                    if intrinsic_eligible is False
                    else "point_not_labeled"
                ),
                "purge_minutes": 0,
            }
        )
    return rows


def build_fold_v2_assignments(
    *,
    label_frame: pd.DataFrame,
    task_id: str,
    spec,
    record_time: dict[str, pd.Timestamp],
    group_lookup: dict[str, str],
    purge_minutes: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    source_rows = label_frame.loc[label_frame["deployment_domain_name"].astype("string") == "P1_SOURCE"].copy()
    for row in source_rows.itertuples(index=False):
        sample_id = str(row.sample_id)
        timestamp = record_time.get(sample_id)
        partition = fold_partition(timestamp, spec)
        if partition is None:
            continue
        effective, exclusion_reason = resolve_v2_effective_partition_for_fold(
            base_partition=partition,
            timestamp=timestamp,
            spec=spec,
            purge_minutes=purge_minutes,
            source_intrinsic_eligibility=bool(getattr(row, "intrinsic_eligibility", str(row.label_status) == "LABELED")),
            source_label_status=str(row.label_status),
            source_exclusion_reason=getattr(row, "intrinsic_exclusion_reason", pd.NA),
        )
        rows.append(
            {
                "sample_id": sample_id,
                "record_id": sample_id,
                "view_id": task_id,
                "protocol_view_id": task_id,
                "fold_id": spec.fold_id,
                "fold_policy_id": getattr(spec, "fold_policy_id", "UNSPECIFIED"),
                "deployment_domain": "P1_SOURCE",
                "base_partition": partition,
                "effective_partition": effective,
                "protocol_eligibility": effective != "excluded",
                "group_id": group_lookup.get(sample_id, sample_id),
                "eligibility_status": "eligible" if effective != "excluded" else "excluded",
                "exclusion_reason": exclusion_reason,
                "purge_minutes": purge_minutes,
            }
        )
    return rows


def build_p2_holdout_view_assignments(
    *,
    point_labels: pd.DataFrame,
    same_y_labels: pd.DataFrame,
    temporal_3h_labels: pd.DataFrame,
    temporal_8h_labels: pd.DataFrame,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for frame, view_id, group_by_record, purge_minutes in (
        (point_labels.loc[point_labels["task_id"] == "v0_point_train"], "v0_point_train", True, 0),
        (point_labels.loc[point_labels["task_id"] == "v1_point_train"], "v1_point_train", True, 0),
        (same_y_labels.loc[same_y_labels["task_id"] == "v2_same_y_3h"], "v2_same_y_3h", True, 180),
        (same_y_labels.loc[same_y_labels["task_id"] == "v2_same_y_8h"], "v2_same_y_8h", True, 480),
        (temporal_3h_labels, "v2_temporal_3h", True, 180),
        (temporal_8h_labels, "v2_temporal_8h", True, 480),
    ):
        source_rows = frame.loc[frame["deployment_domain_name"].astype("string") == "P2_TARGET"].copy()
        for row in source_rows.itertuples(index=False):
            intrinsic_eligible = bool(getattr(row, "intrinsic_eligibility", str(row.label_status) == "LABELED"))
            effective = "target_test" if str(row.label_status) == "LABELED" and intrinsic_eligible else "excluded"
            sample_id = str(row.sample_id)
            rows.append(
                {
                    "sample_id": sample_id,
                    "record_id": sample_id,
                    "view_id": view_id,
                    "protocol_view_id": view_id,
                    "fold_id": "p2_target_holdout",
                    "deployment_domain": "P2_TARGET",
                    "base_partition": "target_test",
                    "effective_partition": effective,
                    "protocol_eligibility": effective != "excluded",
                    "group_id": sample_id,
                    "eligibility_status": "eligible" if effective != "excluded" else "excluded",
                    "exclusion_reason": (
                        pd.NA
                        if effective != "excluded"
                        else getattr(row, "intrinsic_exclusion_reason", pd.NA)
                        if hasattr(row, "intrinsic_exclusion_reason")
                        else "not_labeled"
                    ),
                    "purge_minutes": purge_minutes,
                }
            )
    return rows
