from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from Backend.Benchmark.validity_lifecycle.contracts import EnvironmentSpec


def classify_support_status(
    *,
    total_rows: int,
    class_rows: int,
    day_count: int,
    segment_count: int,
    min_samples: int,
    min_days: int,
    min_segments: int,
) -> str:
    if total_rows <= 0:
        return "NOT_ESTIMABLE"
    if class_rows <= 0:
        return "ABSENT"
    if class_rows >= min_samples and day_count >= min_days and segment_count >= min_segments:
        return "FULL"
    return "LOW_SUPPORT"


def build_environment_support_matrix(
    view_observation_registry: pd.DataFrame,
    *,
    environment_specs: tuple[EnvironmentSpec, ...],
    expected_targets: Iterable[str],
    min_samples: int,
    min_days: int,
    min_segments: int,
) -> pd.DataFrame:
    eligible = view_observation_registry.loc[view_observation_registry["view_eligible"].fillna(False).astype(bool)].copy()
    total_counts = (
        eligible.groupby(["environment_id", "view_id"], dropna=False, sort=False)["sample_id"]
        .count()
        .to_dict()
    )
    rows: list[dict[str, object]] = []
    for spec in environment_specs:
        env_frame = eligible.loc[eligible["environment_id"].astype("string") == spec.environment_id].copy()
        for view_id in sorted(view_observation_registry["view_id"].astype("string").dropna().unique()):
            view_frame = env_frame.loc[env_frame["view_id"].astype("string") == view_id].copy()
            total_rows = int(total_counts.get((spec.environment_id, view_id), 0))
            for target in expected_targets:
                target_frame = view_frame.loc[view_frame["target_label"].astype("string") == target].copy()
                rows.append(
                    {
                        "environment_id": spec.environment_id,
                        "stage_name": spec.stage_name,
                        "deployment_id": spec.deployment_id,
                        "view_id": view_id,
                        "target_label": target,
                        "eligible_row_count": total_rows,
                        "class_row_count": int(len(target_frame)),
                        "class_day_count": int(target_frame["day_id"].astype("string").nunique()) if not target_frame.empty else 0,
                        "class_segment_count": int(target_frame["segment_id"].astype("string").nunique()) if not target_frame.empty else 0,
                        "support_status": classify_support_status(
                            total_rows=total_rows,
                            class_rows=int(len(target_frame)),
                            day_count=int(target_frame["day_id"].astype("string").nunique()) if not target_frame.empty else 0,
                            segment_count=int(target_frame["segment_id"].astype("string").nunique()) if not target_frame.empty else 0,
                            min_samples=min_samples,
                            min_days=min_days,
                            min_segments=min_segments,
                        ),
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def build_label_first_occurrence_audit(
    view_observation_registry: pd.DataFrame,
    environment_specs: tuple[EnvironmentSpec, ...],
    *,
    expected_targets: Iterable[str],
) -> pd.DataFrame:
    point_reference = view_observation_registry.loc[
        (view_observation_registry["view_id"].astype("string") == "v0_point")
        & view_observation_registry["view_eligible"].fillna(False).astype(bool)
    ].copy()
    first_occurrence = (
        point_reference.groupby("target_label", dropna=False, sort=False)["timestamp_local"].min().to_dict()
        if not point_reference.empty
        else {}
    )
    rows: list[dict[str, object]] = []
    for spec in environment_specs:
        env_frame = view_observation_registry.loc[
            view_observation_registry["environment_id"].astype("string") == spec.environment_id
        ].copy()
        for view_id in sorted(view_observation_registry["view_id"].astype("string").dropna().unique()):
            view_frame = env_frame.loc[env_frame["view_id"].astype("string") == view_id].copy()
            for target in expected_targets:
                first_ts = first_occurrence.get(target, pd.NaT)
                present = bool(
                    not view_frame.loc[
                        view_frame["view_eligible"].fillna(False).astype(bool)
                        & view_frame["target_label"].astype("string").eq(target)
                    ].empty
                )
                if present:
                    absence_reason = "present"
                elif pd.isna(first_ts):
                    absence_reason = "never_observed"
                elif first_ts >= spec.end_local:
                    absence_reason = "not_yet_observed"
                else:
                    absence_reason = "filtered_or_unsupported"
                rows.append(
                    {
                        "environment_id": spec.environment_id,
                        "stage_name": spec.stage_name,
                        "view_id": view_id,
                        "target_label": target,
                        "present_in_environment": present,
                        "first_occurrence_timestamp": first_ts,
                        "appeared_before_environment": bool(pd.notna(first_ts) and first_ts < spec.start_local),
                        "absence_reason": absence_reason,
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def build_class_day_segment_support(
    view_observation_registry: pd.DataFrame,
    environment_specs: tuple[EnvironmentSpec, ...],
    *,
    expected_targets: Iterable[str],
) -> pd.DataFrame:
    eligible = view_observation_registry.loc[view_observation_registry["view_eligible"].fillna(False).astype(bool)].copy()
    rows: list[dict[str, object]] = []
    for spec in environment_specs:
        env_frame = eligible.loc[eligible["environment_id"].astype("string") == spec.environment_id].copy()
        for view_id in sorted(eligible["view_id"].astype("string").dropna().unique()):
            view_frame = env_frame.loc[env_frame["view_id"].astype("string") == view_id].copy()
            split_by_day = _build_day_split_lookup(view_frame)
            for target in expected_targets:
                target_frame = view_frame.loc[view_frame["target_label"].astype("string") == target].copy()
                split_counts = _collect_split_counts(target_frame, split_by_day)
                rows.append(
                    {
                        "environment_id": spec.environment_id,
                        "stage_name": spec.stage_name,
                        "view_id": view_id,
                        "target_label": target,
                        "total_row_count": int(len(target_frame)),
                        "total_day_count": int(target_frame["day_id"].astype("string").nunique()) if not target_frame.empty else 0,
                        "total_segment_count": int(target_frame["segment_id"].astype("string").nunique()) if not target_frame.empty else 0,
                        "train_row_count": split_counts["train_row_count"],
                        "validation_row_count": split_counts["validation_row_count"],
                        "test_row_count": split_counts["test_row_count"],
                        "train_day_count": split_counts["train_day_count"],
                        "validation_day_count": split_counts["validation_day_count"],
                        "test_day_count": split_counts["test_day_count"],
                        "linear_split_supported": bool(
                            split_counts["train_row_count"] > 0
                            and split_counts["validation_row_count"] > 0
                            and split_counts["test_row_count"] > 0
                        ),
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def _build_day_split_lookup(view_frame: pd.DataFrame) -> dict[str, str]:
    unique_days = sorted(day for day in view_frame["day_id"].astype("string").dropna().unique())
    if not unique_days:
        return {}
    train_end = max(1, int(round(len(unique_days) * 0.70)))
    validation_end = max(train_end + 1, int(round(len(unique_days) * 0.85)))
    validation_end = min(validation_end, len(unique_days))
    lookup: dict[str, str] = {}
    for index, day_id in enumerate(unique_days):
        if index < train_end:
            lookup[day_id] = "train"
        elif index < validation_end:
            lookup[day_id] = "validation"
        else:
            lookup[day_id] = "test"
    if "validation" not in lookup.values() and len(unique_days) >= 2:
        lookup[unique_days[-1]] = "validation"
    if "test" not in lookup.values() and len(unique_days) >= 3:
        lookup[unique_days[-1]] = "test"
    return lookup


def _collect_split_counts(target_frame: pd.DataFrame, split_by_day: dict[str, str]) -> dict[str, int]:
    if target_frame.empty:
        return {
            "train_row_count": 0,
            "validation_row_count": 0,
            "test_row_count": 0,
            "train_day_count": 0,
            "validation_day_count": 0,
            "test_day_count": 0,
        }
    working = target_frame.copy()
    working["linear_split"] = working["day_id"].astype("string").map(split_by_day).fillna("unknown")
    counts: dict[str, int] = {}
    for split_name in ("train", "validation", "test"):
        split_frame = working.loc[working["linear_split"].astype("string") == split_name].copy()
        counts[f"{split_name}_row_count"] = int(len(split_frame))
        counts[f"{split_name}_day_count"] = int(split_frame["day_id"].astype("string").nunique()) if not split_frame.empty else 0
    return counts
