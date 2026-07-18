from __future__ import annotations

from dataclasses import dataclass
import json

import pandas as pd

MIN_ROW_COMPLETENESS_RATIO = 0.90
MAX_GAP_MULTIPLIER = 2.0
CORE_PRIMARY_VIEWS: tuple[str, ...] = (
    "v0_point_train",
    "v1_point_train",
    "v2_same_y_3h",
    "v2_same_y_8h",
    "v2_temporal_3h",
    "v2_temporal_8h",
)


@dataclass(frozen=True)
class RollingFoldSpec:
    fold_id: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    fold_status: str


def build_calendar_blocks(
    p1_df: pd.DataFrame,
    *,
    block_days: int,
    expected_interval_sec: int,
) -> pd.DataFrame:
    if p1_df.empty:
        return pd.DataFrame()
    start = p1_df["timestamp_local"].min().floor("D")
    final_end = p1_df["timestamp_local"].max().ceil("D")
    rows: list[dict[str, object]] = []
    block_index = 1
    current = start
    while current < final_end:
        block_end = current + pd.Timedelta(days=block_days)
        block_rows = p1_df.loc[
            (p1_df["timestamp_local"] >= current) & (p1_df["timestamp_local"] < block_end)
        ].copy()
        rows.append(
            {
                "block_index": block_index,
                "block_days": block_days,
                "start_time": current,
                "end_time": block_end,
                "row_count": int(len(block_rows)),
                "day_count": int(block_rows["timestamp_local"].dt.floor("D").nunique()) if not block_rows.empty else 0,
                "expected_rows": max(int(round((block_days * 24 * 3600) / max(expected_interval_sec, 1))), 1),
                "observed_expected_ratio": float(len(block_rows) / max(int(round((block_days * 24 * 3600) / max(expected_interval_sec, 1))), 1)),
                "max_internal_gap_sec": max_internal_gap_seconds(block_rows),
            }
        )
        current = block_end
        block_index += 1
    return pd.DataFrame(rows).convert_dtypes()


def build_p1_rolling_fold_specs(
    blocks_df: pd.DataFrame,
    *,
    initial_train_blocks: int,
    validation_blocks: int,
    test_blocks: int,
) -> list[RollingFoldSpec]:
    specs: list[RollingFoldSpec] = []
    total_blocks_needed = initial_train_blocks + validation_blocks + test_blocks
    fold_number = 1
    for test_block_end in range(total_blocks_needed, len(blocks_df) + 1):
        train_end_index = test_block_end - validation_blocks - test_blocks
        validation_end_index = test_block_end - test_blocks
        train_start = pd.Timestamp(blocks_df.loc[blocks_df["block_index"] == 1, "start_time"].iloc[0])
        train_end = pd.Timestamp(blocks_df.loc[blocks_df["block_index"] == train_end_index, "end_time"].iloc[0])
        validation_start = pd.Timestamp(blocks_df.loc[blocks_df["block_index"] == train_end_index + 1, "start_time"].iloc[0])
        validation_end = pd.Timestamp(blocks_df.loc[blocks_df["block_index"] == validation_end_index, "end_time"].iloc[0])
        test_start = pd.Timestamp(blocks_df.loc[blocks_df["block_index"] == validation_end_index + 1, "start_time"].iloc[0])
        test_end = pd.Timestamp(blocks_df.loc[blocks_df["block_index"] == test_block_end, "end_time"].iloc[0])
        test_rows = int(
            blocks_df.loc[
                (blocks_df["block_index"] >= validation_end_index + 1) & (blocks_df["block_index"] <= test_block_end),
                "row_count",
            ].sum()
        )
        if test_rows == 0:
            continue
        fold_status = "full_candidate" if fold_number in {1, 2} else "partial_stress"
        specs.append(
            RollingFoldSpec(
                fold_id=f"fold_{fold_number:02d}",
                train_start=train_start,
                train_end=train_end,
                validation_start=validation_start,
                validation_end=validation_end,
                test_start=test_start,
                test_end=test_end,
                fold_status=fold_status,
            )
        )
        fold_number += 1
    return specs


def annotate_core_fold_status(
    fold_manifest: pd.DataFrame,
    unsupported_class_audit: pd.DataFrame,
) -> pd.DataFrame:
    if fold_manifest.empty:
        return fold_manifest.convert_dtypes()
    result = fold_manifest.copy()
    unsupported = unsupported_class_audit.copy()
    if unsupported.empty:
        result["unsupported_class_reporting_required"] = False
        result["unsupported_views_json"] = "[]"
        return result.convert_dtypes()
    unsupported["unsupported_class_count"] = unsupported["unsupported_classes"].astype("string").map(_unsupported_count)
    core_unsupported = unsupported.loc[
        unsupported["view_id"].astype("string").isin(CORE_PRIMARY_VIEWS)
        & unsupported["unsupported_class_count"].astype(int).gt(0)
    ].copy()
    summary_rows = (
        core_unsupported.groupby(["fold_id", "partition"], dropna=False, sort=False)
        .agg(
            unsupported_class_reporting_required=("unsupported_class_count", lambda s: bool((pd.Series(s).astype(int) > 0).any())),
            unsupported_views_json=(
                "view_id",
                lambda s: json_dumps_compact(sorted(pd.Series(s).astype("string").dropna().unique().tolist())),
            ),
        )
        .reset_index()
    )
    if summary_rows.empty:
        result["unsupported_class_reporting_required"] = False
        result["unsupported_views_json"] = "[]"
        return result.convert_dtypes()
    result = result.merge(summary_rows, on=["fold_id", "partition"], how="left")
    result["unsupported_class_reporting_required"] = result["unsupported_class_reporting_required"].fillna(False).astype(bool)
    result["unsupported_views_json"] = result["unsupported_views_json"].fillna("[]").astype("string")
    mask = (
        result["primary_benchmark_eligible"].astype(bool)
        & result["unsupported_class_reporting_required"].astype(bool)
    )
    result.loc[mask, "fold_status"] = "primary_with_unsupported_class_reporting"
    result.loc[mask, "status_reason"] = "temporal_completeness_passed_with_unsupported_class_reporting"
    return result.convert_dtypes()


def build_p1_5day_support_diagnostic(
    p1_df: pd.DataFrame,
    *,
    expected_interval_sec: int,
    initial_train_blocks: int,
    validation_blocks: int,
    test_blocks: int,
    label_frames: dict[str, pd.DataFrame] | None = None,
    validity_column: str = "core_environment_fully_evaluable",
) -> pd.DataFrame:
    blocks_df = build_calendar_blocks(p1_df, block_days=5, expected_interval_sec=expected_interval_sec)
    specs = build_p1_rolling_fold_specs(
        blocks_df,
        initial_train_blocks=initial_train_blocks,
        validation_blocks=validation_blocks,
        test_blocks=test_blocks,
    )
    return build_fold_quality_manifest(
        fold_specs=specs,
        p1_df=p1_df,
        expected_interval_sec=expected_interval_sec,
        label_frames=label_frames,
        block_days=5,
        validity_column=validity_column,
    )


def build_fold_quality_manifest(
    *,
    fold_specs: list[RollingFoldSpec],
    p1_df: pd.DataFrame,
    expected_interval_sec: int,
    label_frames: dict[str, pd.DataFrame] | None = None,
    view_assignments: pd.DataFrame | None = None,
    boundary_event_audit: pd.DataFrame | None = None,
    block_days: int = 7,
    validity_column: str = "core_environment_fully_evaluable",
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for spec in fold_specs:
        for partition, start, end in (
            ("train", spec.train_start, spec.train_end),
            ("validation", spec.validation_start, spec.validation_end),
            ("test", spec.test_start, spec.test_end),
        ):
            partition_frame = slice_partition_rows(p1_df, start, end, timestamp_column="timestamp_local")
            expected_duration_hours = float((end - start).total_seconds() / 3600.0)
            expected_row_count = expected_partition_rows(start, end, expected_interval_sec)
            observed_row_count = int(len(partition_frame))
            row_completeness_ratio = float(observed_row_count / max(expected_row_count, 1))
            observed_span_hours = _observed_span_hours(partition_frame, timestamp_column="timestamp_local")
            represented_calendar_days = int(partition_frame["timestamp_local"].dt.floor("D").nunique()) if not partition_frame.empty else 0
            largest_gap = max_internal_gap_seconds(partition_frame, timestamp_column="record.ts_sample")
            validity_rate = _validity_rate(partition_frame, validity_column=validity_column)
            boundary_count = _boundary_event_count(boundary_event_audit, spec.fold_id, partition)
            eligible_count_by_view = _eligible_count_by_view(
                label_frames=label_frames,
                view_assignments=view_assignments,
                fold_id=spec.fold_id,
                partition=partition,
                start=start,
                end=end,
            )
            class_support = _class_support_by_view(
                label_frames=label_frames,
                view_assignments=view_assignments,
                fold_id=spec.fold_id,
                partition=partition,
                start=start,
                end=end,
            )
            failed_criteria = _partition_failed_criteria(
                observed_row_count=observed_row_count,
                row_completeness_ratio=row_completeness_ratio,
                largest_internal_gap_seconds=largest_gap,
                expected_interval_sec=expected_interval_sec,
                boundary_event_count=boundary_count,
            )
            generated_successfully = observed_row_count > 0
            primary_benchmark_eligible = bool(generated_successfully and not failed_criteria)
            stress_analysis_eligible = bool(generated_successfully)
            status_reason = (
                "temporal_completeness_passed"
                if primary_benchmark_eligible
                else "temporal_completeness_review_required"
                if generated_successfully
                else "no_partition_rows"
            )
            rows.append(
                {
                    "fold_id": spec.fold_id,
                    "block_days": int(block_days),
                    "fold_status": spec.fold_status,
                    "partition": partition,
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "expected_duration_hours": expected_duration_hours,
                    "observed_span_hours": observed_span_hours,
                    "expected_row_count": expected_row_count,
                    "observed_row_count": observed_row_count,
                    "row_completeness_ratio": row_completeness_ratio,
                    "represented_calendar_days": represented_calendar_days,
                    "largest_internal_gap_seconds": largest_gap,
                    "validity_rate": validity_rate,
                    "boundary_event_count": boundary_count,
                    "eligible_count_by_view": json_dumps_compact(eligible_count_by_view),
                    "class_support_by_task": json_dumps_compact(class_support),
                    "generated_successfully": generated_successfully,
                    "primary_benchmark_eligible": primary_benchmark_eligible,
                    "stress_analysis_eligible": stress_analysis_eligible,
                    "status_reason": status_reason,
                    "failed_criteria": json_dumps_compact(failed_criteria),
                }
            )
    return pd.DataFrame(rows).convert_dtypes()


def slice_partition_rows(
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    timestamp_column: str = "timestamp_local",
) -> pd.DataFrame:
    return frame.loc[(frame[timestamp_column] >= start) & (frame[timestamp_column] < end)].copy()


def expected_partition_rows(start: pd.Timestamp, end: pd.Timestamp, expected_interval_sec: int) -> int:
    duration_seconds = int((end - start).total_seconds())
    return max(int(round(duration_seconds / max(expected_interval_sec, 1))), 1)


def max_internal_gap_seconds(frame: pd.DataFrame, *, timestamp_column: str = "record.ts_sample") -> int | None:
    if frame.empty:
        return None
    timestamps = pd.to_numeric(frame[timestamp_column], errors="coerce").dropna().sort_values()
    if len(timestamps) < 2:
        return 0
    return int(timestamps.diff().dropna().max())


def _coverage_ratio(
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    expected_interval_sec: int,
) -> float:
    expected = max(expected_partition_rows(start, end, expected_interval_sec), 1)
    return float(len(frame) / expected)


def _partition_failed_criteria(
    *,
    observed_row_count: int,
    row_completeness_ratio: float,
    largest_internal_gap_seconds: int | None,
    expected_interval_sec: int,
    boundary_event_count: int,
) -> list[str]:
    failed: list[str] = []
    if observed_row_count == 0:
        failed.append("no_observed_rows")
    if row_completeness_ratio < MIN_ROW_COMPLETENESS_RATIO:
        failed.append(f"row_completeness_below_{MIN_ROW_COMPLETENESS_RATIO:.2f}")
    gap_threshold = int(expected_interval_sec * MAX_GAP_MULTIPLIER)
    if largest_internal_gap_seconds is not None and largest_internal_gap_seconds > gap_threshold:
        failed.append(f"internal_gap_above_{MAX_GAP_MULTIPLIER:.1f}x_expected_cadence")
    return failed


def _unsupported_count(payload: str) -> int:
    if not payload or payload == "[]" or payload == "<NA>":
        return 0
    values = json.loads(payload)
    return int(len(values))


def _class_support_by_view(
    *,
    label_frames: dict[str, pd.DataFrame] | None,
    view_assignments: pd.DataFrame | None,
    fold_id: str,
    partition: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, dict[str, int]]:
    if not label_frames:
        return {}
    support: dict[str, dict[str, int]] = {}
    for view_id, frame in label_frames.items():
        if view_assignments is not None and not view_assignments.empty:
            eligible_ids = _eligible_ids_from_assignments(view_assignments, fold_id, partition, view_id)
            if eligible_ids:
                selected = frame.loc[frame["sample_id"].astype("string").isin(eligible_ids)].copy()
                support[view_id] = _label_count_dict(selected)
                continue
        timestamp_series = _resolve_label_timestamp_series(frame)
        if timestamp_series is None:
            continue
        mask = (timestamp_series >= start) & (timestamp_series < end)
        if "label_status" in frame.columns:
            mask = mask & (frame["label_status"].astype("string") == "LABELED")
        elif "effective_partition" in frame.columns:
            mask = mask & (frame["effective_partition"].astype("string") != "excluded")
        selected = frame.loc[mask].copy()
        support[view_id] = _label_count_dict(selected)
    return support


def _eligible_count_by_view(
    *,
    label_frames: dict[str, pd.DataFrame] | None,
    view_assignments: pd.DataFrame | None,
    fold_id: str,
    partition: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, int]:
    if view_assignments is not None and not view_assignments.empty:
        filtered = view_assignments.loc[
            (view_assignments["fold_id"].astype("string") == fold_id)
            & (view_assignments["effective_partition"].astype("string") == partition)
        ].copy()
        if not filtered.empty:
            return {
                str(view_id): int(count)
                for view_id, count in filtered["view_id"].astype("string").value_counts(sort=False).items()
            }
    if not label_frames:
        return {}
    counts: dict[str, int] = {}
    for view_id, frame in label_frames.items():
        timestamp_series = _resolve_label_timestamp_series(frame)
        if timestamp_series is None:
            continue
        mask = (timestamp_series >= start) & (timestamp_series < end)
        if "label_status" in frame.columns:
            mask = mask & (frame["label_status"].astype("string") == "LABELED")
        elif "effective_partition" in frame.columns:
            mask = mask & (frame["effective_partition"].astype("string") != "excluded")
        counts[view_id] = int(mask.sum())
    return counts


def _eligible_ids_from_assignments(
    view_assignments: pd.DataFrame,
    fold_id: str,
    partition: str,
    view_id: str,
) -> set[str]:
    filtered = view_assignments.loc[
        (view_assignments["fold_id"].astype("string") == fold_id)
        & (view_assignments["view_id"].astype("string") == view_id)
        & (view_assignments["effective_partition"].astype("string") == partition)
    ]
    return set(filtered["sample_id"].astype("string").tolist())


def _label_count_dict(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty:
        return {}
    return {
        str(label): int(count)
        for label, count in frame["label_name"].astype("string").value_counts(dropna=False).items()
    }


def _resolve_label_timestamp_series(frame: pd.DataFrame) -> pd.Series | None:
    if frame.empty:
        return pd.Series(dtype="datetime64[ns, Asia/Ho_Chi_Minh]")
    if "sample_id" not in frame.columns:
        return None
    record_timestamp = frame["sample_id"].astype("string").map(_sample_id_to_timestamp)
    return pd.Series(pd.DatetimeIndex(record_timestamp), index=frame.index)


def _sample_id_to_timestamp(sample_id: str) -> pd.Timestamp | pd.NaT:
    parts = str(sample_id).split(":")
    if len(parts) < 3:
        return pd.NaT
    ts_numeric = pd.to_numeric(pd.Series([parts[-1]]), errors="coerce").iloc[0]
    if pd.isna(ts_numeric):
        return pd.NaT
    return pd.to_datetime(int(ts_numeric), unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh")


def json_dumps_compact(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _observed_span_hours(frame: pd.DataFrame, *, timestamp_column: str) -> float:
    if frame.empty:
        return 0.0
    timestamp_values = pd.to_datetime(frame[timestamp_column], errors="coerce").dropna()
    if timestamp_values.empty:
        return 0.0
    return float((timestamp_values.max() - timestamp_values.min()).total_seconds() / 3600.0)


def _validity_rate(frame: pd.DataFrame, *, validity_column: str) -> float | object:
    if frame.empty or validity_column not in frame.columns:
        return pd.NA
    validity = frame[validity_column].astype("boolean")
    if validity.dropna().empty:
        return pd.NA
    return float(validity.fillna(False).mean())


def _boundary_event_count(
    boundary_event_audit: pd.DataFrame | None,
    fold_id: str,
    partition: str,
) -> int:
    if boundary_event_audit is None or boundary_event_audit.empty:
        return 0
    filtered = boundary_event_audit.loc[
        (boundary_event_audit["fold_id"].astype("string") == fold_id)
        & (
            (boundary_event_audit["start_partition"].astype("string") == partition)
            | (boundary_event_audit["end_partition"].astype("string") == partition)
        )
    ]
    return int(len(filtered))
