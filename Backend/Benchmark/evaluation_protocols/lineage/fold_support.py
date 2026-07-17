from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.evaluation_protocols.diagnostics.folds import (
    expected_partition_rows,
    max_internal_gap_seconds,
    slice_partition_rows,
)
from Backend.Benchmark.evaluation_protocols.lineage.common import EXPECTED_LABELS_BY_VIEW


def build_fold_manifest_rows(
    *,
    spec,
    p1_records: pd.DataFrame,
    expected_interval_sec: int,
    label_frames: dict[str, pd.DataFrame],
    view_rows: list[dict[str, object]],
    boundary_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    view_assignments = pd.DataFrame(view_rows).convert_dtypes()
    boundary_frame = pd.DataFrame(boundary_rows).convert_dtypes()
    for partition, start, end in (
        ("train", spec.train_start, spec.train_end),
        ("validation", spec.validation_start, spec.validation_end),
        ("test", spec.test_start, spec.test_end),
    ):
        partition_frame = slice_partition_rows(p1_records, start, end, timestamp_column="timestamp_local")
        eligible_counts = eligible_counts_for_partition(view_assignments, spec.fold_id, partition)
        rows.append(
            {
                "fold_id": spec.fold_id,
                "fold_status": spec.fold_status,
                "partition": partition,
                "simulation_note": "past_to_future_within_p1",
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "duration_days": int((end - start).days),
                "observed_rows": int(len(partition_frame)),
                "expected_rows": expected_partition_rows(start, end, expected_interval_sec),
                "coverage_ratio": float(
                    len(partition_frame) / max(expected_partition_rows(start, end, expected_interval_sec), 1)
                ),
                "max_internal_gap_sec": max_internal_gap_seconds(partition_frame, timestamp_column="record.ts_sample"),
                "usable_partition": bool(len(partition_frame) > 0),
                "eligible_count_by_view": json.dumps(eligible_counts, ensure_ascii=False, separators=(",", ":")),
                "observed_labels_by_view": json.dumps(
                    label_counts_for_partition(
                        fold_id=spec.fold_id,
                        partition=partition,
                        label_frames=label_frames,
                        view_assignments=view_assignments,
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "boundary_event_count": int(
                    len(boundary_frame.loc[boundary_frame["fold_id"].astype("string") == spec.fold_id])
                )
                if not boundary_frame.empty
                else 0,
            }
        )
    return rows


def build_unsupported_rows_for_fold(
    *,
    spec,
    label_frames: dict[str, pd.DataFrame],
    view_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    view_assignments = pd.DataFrame(view_rows).convert_dtypes()
    for partition in ("train", "validation", "test"):
        for view_id, expected_labels in EXPECTED_LABELS_BY_VIEW.items():
            eligible_ids = eligible_sample_ids(view_assignments, spec.fold_id, partition, view_id)
            observed_labels = observed_labels_for_ids(label_frames[view_id], eligible_ids)
            unsupported = [label for label in expected_labels if label not in observed_labels]
            rows.append(
                {
                    "fold_id": spec.fold_id,
                    "partition": partition,
                    "view_id": view_id,
                    "eligible_sample_count": int(len(eligible_ids)),
                    "observed_labels": json.dumps(observed_labels, ensure_ascii=False, separators=(",", ":")),
                    "unsupported_classes": json.dumps(unsupported, ensure_ascii=False, separators=(",", ":")),
                }
            )
    return rows


def append_matched_rows_for_fold(
    *,
    spec,
    matched_rows: dict[str, list[dict[str, object]]],
    view_rows: list[dict[str, object]],
    label_frames: dict[str, pd.DataFrame],
) -> None:
    view_assignments = pd.DataFrame(view_rows).convert_dtypes()
    point_lookup = {
        "v0_point_train": label_frames["v0_point_train"].set_index("sample_id")["label_name"].astype("string").to_dict(),
        "v1_point_train": label_frames["v1_point_train"].set_index("sample_id")["label_name"].astype("string").to_dict(),
    }
    same_y_lookup = {
        "v2_same_y_3h": label_frames["v2_same_y_3h"].set_index("sample_id")["label_name"].astype("string").to_dict(),
        "v2_same_y_8h": label_frames["v2_same_y_8h"].set_index("sample_id")["label_name"].astype("string").to_dict(),
    }
    for point_task, v2_task, filename in (
        ("v0_point_train", "v2_same_y_3h", "matched_v0_v2_3h.csv"),
        ("v1_point_train", "v2_same_y_3h", "matched_v1_v2_3h.csv"),
        ("v0_point_train", "v2_same_y_8h", "matched_v0_v2_8h.csv"),
        ("v1_point_train", "v2_same_y_8h", "matched_v1_v2_8h.csv"),
    ):
        for partition in ("train", "validation", "test"):
            point_ids = eligible_sample_ids(view_assignments, spec.fold_id, partition, point_task)
            v2_ids = eligible_sample_ids(view_assignments, spec.fold_id, partition, v2_task)
            for record_id in sorted(point_ids & v2_ids):
                matched_rows[filename].append(
                    {
                        "fold_id": spec.fold_id,
                        "partition": partition,
                        "record_id": record_id,
                        "point_task_id": point_task,
                        "v2_task_id": v2_task,
                        "point_label_name": point_lookup[point_task].get(record_id, pd.NA),
                        "v2_label_name": same_y_lookup[v2_task].get(record_id, pd.NA),
                    }
                )


def eligible_counts_for_partition(view_assignments: pd.DataFrame, fold_id: str, partition: str) -> dict[str, int]:
    if view_assignments.empty:
        return {}
    filtered = view_assignments.loc[
        (view_assignments["fold_id"].astype("string") == fold_id)
        & (view_assignments["effective_partition"].astype("string") == partition)
    ].copy()
    if filtered.empty:
        return {}
    return {
        str(view_id): int(count)
        for view_id, count in filtered["view_id"].astype("string").value_counts(sort=False).items()
    }


def label_counts_for_partition(
    *,
    fold_id: str,
    partition: str,
    label_frames: dict[str, pd.DataFrame],
    view_assignments: pd.DataFrame,
) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for view_id, frame in label_frames.items():
        eligible_ids = eligible_sample_ids(view_assignments, fold_id, partition, view_id)
        if not eligible_ids:
            counts[view_id] = {}
            continue
        filtered = frame.loc[frame["sample_id"].astype("string").isin(eligible_ids)].copy()
        counts[view_id] = {
            str(label): int(count)
            for label, count in filtered["label_name"].astype("string").value_counts(sort=False).items()
        }
    return counts


def eligible_sample_ids(
    view_assignments: pd.DataFrame,
    fold_id: str,
    partition: str,
    view_id: str,
) -> set[str]:
    if view_assignments.empty:
        return set()
    filtered = view_assignments.loc[
        (view_assignments["fold_id"].astype("string") == fold_id)
        & (view_assignments["view_id"].astype("string") == view_id)
        & (view_assignments["effective_partition"].astype("string") == partition)
    ]
    return set(filtered["sample_id"].astype("string").tolist())


def observed_labels_for_ids(frame: pd.DataFrame, sample_ids: set[str]) -> list[str]:
    if not sample_ids:
        return []
    return sorted(
        frame.loc[frame["sample_id"].astype("string").isin(sample_ids), "label_name"]
        .astype("string")
        .dropna()
        .unique()
        .tolist()
    )
