from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.evaluation_protocols.lineage.common import EXPECTED_LABELS_BY_VIEW


MIN_ESTIMABLE_CLASS_SUPPORT = 5

VIEW_TO_PROTOCOL_KEY: dict[str, str] = {
    "v0_point": "v0_point_train",
    "v1_point": "v1_point_train",
    "v2_same_y_mini_3h": "v2_same_y_3h",
    "v2_same_y_full_3h": "v2_same_y_3h",
    "v2_same_y_mini_8h": "v2_same_y_8h",
    "v2_same_y_full_8h": "v2_same_y_8h",
}


@dataclass(frozen=True)
class EstimabilityArtifacts:
    matrix: pd.DataFrame


def build_estimability_artifacts(
    *,
    task_training_manifest: pd.DataFrame,
    comparison_training_manifest: pd.DataFrame,
    frozen_target_manifest: pd.DataFrame,
) -> EstimabilityArtifacts:
    rows: list[dict[str, object]] = []
    rows.extend(_build_task_rows(task_training_manifest))
    rows.extend(_build_comparison_rows(comparison_training_manifest))
    rows.extend(_build_frozen_target_rows(frozen_target_manifest))
    matrix = pd.DataFrame(rows).convert_dtypes()
    return EstimabilityArtifacts(matrix=matrix)


def _build_task_rows(task_training_manifest: pd.DataFrame) -> list[dict[str, object]]:
    frame = task_training_manifest.loc[
        task_training_manifest["final_trainability"].fillna(False).astype(bool)
    ].copy()
    rows: list[dict[str, object]] = []
    group_columns = [
        "feature_view_id",
        "label_task_id",
        "protocol_view_id",
        "fold_id",
        "partition",
        "deployment_domain",
        "effective_partition",
    ]
    for keys, group in frame.groupby(group_columns, dropna=False, sort=False):
        row = dict(zip(group_columns, keys, strict=True))
        expected_labels = _expected_labels(row["label_task_id"], row["feature_view_id"])
        counts = _count_expected_labels(group["label_name"], expected_labels)
        rows.append(
            _build_state_row(
                scope_type="task",
                benchmark_scope_id=str(row["feature_view_id"]),
                comparison_id=pd.NA,
                comparison_side=pd.NA,
                matched_cohort_id=pd.NA,
                feature_view_id=str(row["feature_view_id"]),
                label_task_id=str(row["label_task_id"]),
                protocol_view_id=str(row["protocol_view_id"]),
                fold_id=str(row["fold_id"]),
                partition=str(row["partition"]),
                deployment_domain=str(row["deployment_domain"]),
                effective_partition=str(row["effective_partition"]),
                counts=counts,
                expected_labels=expected_labels,
                sample_count=int(len(group)),
            )
        )
    return rows


def _build_comparison_rows(comparison_training_manifest: pd.DataFrame) -> list[dict[str, object]]:
    frame = comparison_training_manifest.loc[
        comparison_training_manifest["final_trainability"].fillna(False).astype(bool)
    ].copy()
    rows: list[dict[str, object]] = []
    group_columns = [
        "comparison_id",
        "comparison_side",
        "matched_cohort_id",
        "feature_view_id",
        "label_task_id",
        "protocol_view_id",
        "fold_id",
        "partition",
    ]
    for keys, group in frame.groupby(group_columns, dropna=False, sort=False):
        row = dict(zip(group_columns, keys, strict=True))
        expected_labels = _expected_labels(row["label_task_id"], row["feature_view_id"])
        counts = _count_expected_labels(group["label_name"], expected_labels)
        rows.append(
            _build_state_row(
                scope_type="comparison",
                benchmark_scope_id=str(row["comparison_id"]),
                comparison_id=str(row["comparison_id"]),
                comparison_side=str(row["comparison_side"]),
                matched_cohort_id=str(row["matched_cohort_id"]),
                feature_view_id=str(row["feature_view_id"]),
                label_task_id=str(row["label_task_id"]),
                protocol_view_id=str(row["protocol_view_id"]),
                fold_id=str(row["fold_id"]),
                partition=str(row["partition"]),
                deployment_domain="P1_SOURCE",
                effective_partition=str(row["partition"]),
                counts=counts,
                expected_labels=expected_labels,
                sample_count=int(len(group)),
            )
        )
    return rows


def _build_frozen_target_rows(frozen_target_manifest: pd.DataFrame) -> list[dict[str, object]]:
    frame = frozen_target_manifest.loc[
        frozen_target_manifest["final_trainability"].fillna(False).astype(bool)
    ].copy()
    rows: list[dict[str, object]] = []
    group_columns = [
        "feature_view_id",
        "label_task_id",
        "protocol_view_id",
        "fold_id",
        "partition",
        "deployment_domain",
        "effective_partition",
        "source_manifest_role",
    ]
    for keys, group in frame.groupby(group_columns, dropna=False, sort=False):
        row = dict(zip(group_columns, keys, strict=True))
        expected_labels = _expected_labels(row["label_task_id"], row["feature_view_id"])
        counts = _count_expected_labels(group["label_name"], expected_labels)
        rows.append(
            _build_state_row(
                scope_type="frozen_target",
                benchmark_scope_id=str(row["feature_view_id"]),
                comparison_id=pd.NA,
                comparison_side=pd.NA,
                matched_cohort_id=pd.NA,
                feature_view_id=str(row["feature_view_id"]),
                label_task_id=str(row["label_task_id"]),
                protocol_view_id=str(row["protocol_view_id"]),
                fold_id=str(row["fold_id"]),
                partition=str(row["partition"]),
                deployment_domain=str(row["deployment_domain"]),
                effective_partition=str(row["effective_partition"]),
                counts=counts,
                expected_labels=expected_labels,
                sample_count=int(len(group)),
                source_manifest_role=str(row["source_manifest_role"]),
            )
        )
    return rows


def _build_state_row(
    *,
    scope_type: str,
    benchmark_scope_id: str,
    comparison_id,
    comparison_side,
    matched_cohort_id,
    feature_view_id: str,
    label_task_id: str,
    protocol_view_id: str,
    fold_id: str,
    partition: str,
    deployment_domain: str,
    effective_partition: str,
    counts: dict[str, int],
    expected_labels: tuple[str, ...],
    sample_count: int,
    source_manifest_role: str | pd._libs.missing.NAType = pd.NA,
) -> dict[str, object]:
    missing = [label for label in expected_labels if counts.get(label, 0) == 0]
    supported = [label for label in expected_labels if counts.get(label, 0) > 0]
    sparse = [label for label in expected_labels if 0 < counts.get(label, 0) < MIN_ESTIMABLE_CLASS_SUPPORT]
    strong_support = [label for label in expected_labels if counts.get(label, 0) >= MIN_ESTIMABLE_CLASS_SUPPORT]

    trainability_state = pd.NA
    selection_state = pd.NA
    estimability_state = pd.NA
    role_state = "NOT_ESTIMABLE"
    state_reason = "insufficient_class_support"

    if effective_partition == "train":
        if not missing:
            trainability_state = "TRAINABLE"
            role_state = "TRAINABLE"
            state_reason = "all_expected_classes_present_in_train"
        else:
            trainability_state = "NOT_ESTIMABLE"
            role_state = "NOT_ESTIMABLE"
            state_reason = "missing_expected_classes_in_train"
    elif effective_partition == "validation":
        if not missing:
            selection_state = "SELECTABLE"
            role_state = "SELECTABLE"
            state_reason = "all_expected_classes_present_in_validation"
        else:
            selection_state = "NOT_ESTIMABLE"
            role_state = "NOT_ESTIMABLE"
            state_reason = "missing_expected_classes_in_validation"
    elif effective_partition in {"test", "target_test"}:
        if not missing and not sparse:
            estimability_state = "FULLY_ESTIMABLE"
            role_state = "FULLY_ESTIMABLE"
            state_reason = "all_expected_classes_present_with_min_support"
        elif len(strong_support) >= 2:
            estimability_state = "PARTIALLY_ESTIMABLE"
            role_state = "PARTIALLY_ESTIMABLE"
            state_reason = "comparison_possible_but_class_support_is_incomplete"
        else:
            estimability_state = "NOT_ESTIMABLE"
            role_state = "NOT_ESTIMABLE"
            state_reason = "fewer_than_two_classes_with_min_support"

    return {
        "scope_type": scope_type,
        "benchmark_scope_id": benchmark_scope_id,
        "comparison_id": comparison_id,
        "comparison_side": comparison_side,
        "matched_cohort_id": matched_cohort_id,
        "feature_view_id": feature_view_id,
        "label_task_id": label_task_id,
        "protocol_view_id": protocol_view_id,
        "fold_id": fold_id,
        "partition": partition,
        "deployment_domain": deployment_domain,
        "effective_partition": effective_partition,
        "source_manifest_role": source_manifest_role,
        "sample_count": int(sample_count),
        "expected_class_count": int(len(expected_labels)),
        "present_class_count": int(len(supported)),
        "strong_support_class_count": int(len(strong_support)),
        "min_estimable_class_support": int(MIN_ESTIMABLE_CLASS_SUPPORT),
        "class_counts_json": json.dumps(counts, ensure_ascii=False, separators=(",", ":")),
        "present_classes_json": json.dumps(supported, ensure_ascii=False, separators=(",", ":")),
        "missing_classes_json": json.dumps(missing, ensure_ascii=False, separators=(",", ":")),
        "sparse_classes_json": json.dumps(sparse, ensure_ascii=False, separators=(",", ":")),
        "trainability_state": trainability_state,
        "selection_state": selection_state,
        "estimability_state": estimability_state,
        "role_state": role_state,
        "state_reason": state_reason,
    }


def _expected_labels(label_task_id: str, feature_view_id: str) -> tuple[str, ...]:
    if label_task_id in EXPECTED_LABELS_BY_VIEW:
        return EXPECTED_LABELS_BY_VIEW[label_task_id]
    protocol_key = VIEW_TO_PROTOCOL_KEY.get(str(feature_view_id))
    if protocol_key is not None:
        return EXPECTED_LABELS_BY_VIEW[protocol_key]
    raise KeyError(
        "No expected-label ontology mapping was found for "
        f"label_task_id={label_task_id!r}, feature_view_id={feature_view_id!r}."
    )


def _count_expected_labels(series: pd.Series, expected_labels: tuple[str, ...]) -> dict[str, int]:
    raw_counts = (
        series.astype("string")
        .dropna()
        .value_counts(sort=False)
        .to_dict()
    )
    return {label: int(raw_counts.get(label, 0)) for label in expected_labels}
