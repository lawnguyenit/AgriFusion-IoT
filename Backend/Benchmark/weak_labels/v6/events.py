from __future__ import annotations

from dataclasses import dataclass
import json

import pandas as pd

from Backend.Benchmark.weak_labels.shared.configs import LABEL_STATUS_EXCLUDED_WINDOW, LABEL_STATUS_LABELED, POINT_LABELS, V6_EVENT_LABELS, V6_LOW_RUN_MIN_STEPS
from Backend.Benchmark.weak_labels.shared.helpers import json_dumps_compact, local_time_bucket


@dataclass(frozen=True)
class V6EventArtifacts:
    event_labels: pd.DataFrame
    membership: pd.DataFrame
    boundary_event_audit: pd.DataFrame


def build_event_tables(raw_event_df: pd.DataFrame) -> V6EventArtifacts:
    event_rows, membership_rows = _build_event_rows(raw_event_df)
    event_df = pd.DataFrame(event_rows).convert_dtypes()
    membership_df = pd.DataFrame(membership_rows).convert_dtypes()
    boundary_event_audit = event_df.loc[event_df["boundary_status"].astype("string") != "within_partition"].copy()

    matched_normal_rows = _build_matched_normal_events(raw_event_df, event_df, membership_df)
    if matched_normal_rows:
        event_df = pd.concat([event_df, pd.DataFrame(matched_normal_rows).convert_dtypes()], ignore_index=True)
        membership_df = pd.concat(
            [
                membership_df,
                pd.DataFrame(_membership_rows_from_normal_events(raw_event_df, matched_normal_rows)).convert_dtypes(),
            ],
            ignore_index=True,
        )
    return V6EventArtifacts(
        event_labels=event_df.convert_dtypes(),
        membership=membership_df.convert_dtypes(),
        boundary_event_audit=boundary_event_audit.convert_dtypes(),
    )


def _build_event_rows(raw_event_df: pd.DataFrame) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    memberships: list[dict[str, object]] = []
    event_index = 0
    ordered = raw_event_df.sort_values(["record.ts_sample", "record.id"], kind="stable").reset_index(drop=True)
    active_group: list[pd.Series] = []
    active_kind: str | None = None

    def flush_active_group() -> None:
        nonlocal event_index, active_group, active_kind
        if not active_group or active_kind is None:
            active_group = []
            active_kind = None
            return
        event_index += 1
        event_id = f"v6_evt_{event_index:05d}"
        event_payload, membership_payload = _materialize_event_payload(event_id, active_group, active_kind)
        rows.append(event_payload)
        memberships.extend(membership_payload)
        active_group = []
        active_kind = None

    for _, row in ordered.iterrows():
        point_label = str(row.get("point_train_label_name", ""))
        if point_label == POINT_LABELS[0] or str(row.get("point_label_status", "")) != LABEL_STATUS_LABELED:
            flush_active_group()
            continue
        event_kind = "persistent_low_relative_moisture_event" if point_label == POINT_LABELS[1] else "unknown_environment_event"
        if active_group:
            previous = active_group[-1]
            same_group = (
                str(previous.get("raw_continuity_chunk_id")) == str(row.get("raw_continuity_chunk_id"))
                and point_label == str(previous.get("point_train_label_name"))
            )
            if not same_group:
                flush_active_group()
        active_kind = event_kind
        active_group.append(row)
    flush_active_group()
    return rows, memberships


def _materialize_event_payload(
    event_id: str,
    rows: list[pd.Series],
    event_kind: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    group_df = pd.DataFrame(rows).convert_dtypes()
    base_partitions = group_df["base_partition"].astype("string").dropna().unique().tolist()
    record_count = int(len(group_df))
    if event_kind == "persistent_low_relative_moisture_event" and record_count < V6_LOW_RUN_MIN_STEPS:
        event_kind = "unknown_environment_event"
    boundary_status = "within_partition" if len(base_partitions) == 1 else "crosses_base_partition"
    effective_partition = base_partitions[0] if len(base_partitions) == 1 else "excluded"
    exclusion_reason = pd.NA if len(base_partitions) == 1 else "boundary_event"
    start_local = pd.Timestamp(group_df["timestamp_local"].iloc[0])
    end_local = pd.Timestamp(group_df["timestamp_local"].iloc[-1])
    event_payload = {
        "sample_id": event_id,
        "sample_type": "event",
        "task_id": "v6_event",
        "label_name": event_kind,
        "label_status": LABEL_STATUS_LABELED if effective_partition != "excluded" else LABEL_STATUS_EXCLUDED_WINDOW,
        "base_partition": json_dumps_compact(base_partitions),
        "effective_partition": effective_partition,
        "boundary_status": boundary_status,
        "exclusion_reason": exclusion_reason,
        "record_count": record_count,
        "record_ids": json_dumps_compact(group_df["record.id"].astype("string").tolist()),
        "record.segment_id": str(group_df["record.segment_id"].iloc[0]),
        "raw_continuity_chunk_id": str(group_df["raw_continuity_chunk_id"].iloc[0]),
        "event_start_local": start_local.isoformat(),
        "event_end_local": end_local.isoformat(),
        "time_of_day_bucket": local_time_bucket(start_local),
        "matched_to_event_id": pd.NA,
    }
    memberships = [
        {"record.id": str(record_id), "event_id": event_id, "event_label_name": event_kind}
        for record_id in group_df["record.id"].astype("string").tolist()
    ]
    return event_payload, memberships


def _build_matched_normal_events(
    raw_event_df: pd.DataFrame,
    event_df: pd.DataFrame,
    membership_df: pd.DataFrame,
) -> list[dict[str, object]]:
    if event_df.empty:
        return []
    used_record_ids = set(membership_df["record.id"].astype("string").tolist()) if not membership_df.empty else set()
    normal_rows = raw_event_df.loc[
        (raw_event_df["point_train_label_name"].astype("string") == POINT_LABELS[0])
        & (raw_event_df["point_label_status"].astype("string") == LABEL_STATUS_LABELED)
    ].copy()
    matched_rows: list[dict[str, object]] = []
    normal_run_index = 0
    for event in event_df.to_dict(orient="records"):
        if event["effective_partition"] == "excluded" or event["label_name"] not in {V6_EVENT_LABELS[1], V6_EVENT_LABELS[2]}:
            continue
        candidate = normal_rows.loc[
            (~normal_rows["record.id"].astype("string").isin(used_record_ids))
            & (normal_rows["record.segment_id"].astype("string") == str(event["record.segment_id"]))
            & (normal_rows["base_partition"].astype("string") == str(event["effective_partition"]))
        ].copy()
        if candidate.empty:
            continue
        candidate["time_bucket"] = candidate["timestamp_local"].apply(local_time_bucket)
        candidate = candidate.loc[candidate["time_bucket"] == str(event["time_of_day_bucket"])].copy()
        if candidate.empty:
            continue
        candidate = candidate.sort_values(["record.ts_sample", "record.id"], kind="stable")
        selected = candidate.head(int(event["record_count"])).copy()
        if len(selected) < int(event["record_count"]):
            continue
        normal_run_index += 1
        normal_event_id = f"v6_norm_{normal_run_index:05d}"
        used_record_ids.update(selected["record.id"].astype("string").tolist())
        matched_rows.append(
            {
                "sample_id": normal_event_id,
                "sample_type": "event",
                "task_id": "v6_event",
                "label_name": V6_EVENT_LABELS[0],
                "label_status": LABEL_STATUS_LABELED,
                "base_partition": json_dumps_compact(sorted(selected["base_partition"].astype("string").dropna().unique().tolist())),
                "effective_partition": str(selected["base_partition"].iloc[0]),
                "boundary_status": "within_partition",
                "exclusion_reason": pd.NA,
                "record_count": int(len(selected)),
                "record_ids": json_dumps_compact(selected["record.id"].astype("string").tolist()),
                "record.segment_id": str(selected["record.segment_id"].iloc[0]),
                "raw_continuity_chunk_id": str(selected["raw_continuity_chunk_id"].iloc[0]),
                "event_start_local": pd.Timestamp(selected["timestamp_local"].iloc[0]).isoformat(),
                "event_end_local": pd.Timestamp(selected["timestamp_local"].iloc[-1]).isoformat(),
                "time_of_day_bucket": local_time_bucket(pd.Timestamp(selected["timestamp_local"].iloc[0])),
                "matched_to_event_id": event["sample_id"],
            }
        )
    return matched_rows


def _membership_rows_from_normal_events(
    raw_event_df: pd.DataFrame,
    normal_event_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    memberships: list[dict[str, object]] = []
    lookup_ids = set(raw_event_df["record.id"].astype("string").tolist())
    for row in normal_event_rows:
        raw_record_ids = row["record_ids"]
        record_ids = json.loads(raw_record_ids) if isinstance(raw_record_ids, str) else raw_record_ids
        for record_id in pd.Series(record_ids).astype("string").tolist():
            if record_id not in lookup_ids:
                continue
            memberships.append({"record.id": record_id, "event_id": row["sample_id"], "event_label_name": row["label_name"]})
    return memberships
