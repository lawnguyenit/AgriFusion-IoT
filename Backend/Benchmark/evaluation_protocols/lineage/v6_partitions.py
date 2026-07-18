from __future__ import annotations

import json

import pandas as pd

from Backend.Benchmark.evaluation_protocols.lineage.common import fold_partition


def build_fold_v6_event_assignments(
    *,
    v6_events: pd.DataFrame,
    spec,
    record_domain: dict[str, str],
    record_segment: dict[str, str],
    record_time: dict[str, pd.Timestamp],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    boundary_rows: list[dict[str, object]] = []
    for row in v6_events.to_dict(orient="records"):
        record_ids = json.loads(str(row["record_ids"]))
        member_domains = sorted({record_domain.get(str(record_id), "UNKNOWN") for record_id in record_ids})
        member_segments = sorted({record_segment.get(str(record_id), "UNKNOWN") for record_id in record_ids})
        member_times = [record_time.get(str(record_id)) for record_id in record_ids]
        if any(timestamp is None or pd.isna(timestamp) for timestamp in member_times):
            raise ValueError(f"V6 event {row['sample_id']} has member record_ids without canonical timestamps.")
        event_segment = str(row["record.segment_id"])
        event_domain = "P1_SOURCE" if event_segment == "node1_seg_0001" else "P2_TARGET" if event_segment == "node1_seg_0002" else "UNKNOWN"
        if event_domain == "UNKNOWN":
            raise ValueError(f"V6 event {row['sample_id']} has unsupported segment lineage: {event_segment}.")
        if len(member_domains) != 1 or member_domains[0] != event_domain:
            raise ValueError(
                f"V6 event {row['sample_id']} violates deployment lineage: event_domain={event_domain}, member_domains={member_domains}."
            )
        if len(member_segments) != 1 or member_segments[0] != event_segment:
            raise ValueError(
                f"V6 event {row['sample_id']} violates segment lineage: event_segment={event_segment}, member_segments={member_segments}."
            )
        if event_segment == "node1_seg_0001" and event_domain != "P1_SOURCE":
            raise ValueError(f"Event {row['sample_id']} cannot map node1_seg_0001 to {event_domain}.")
        if event_segment == "node1_seg_0002" and event_domain != "P2_TARGET":
            raise ValueError(f"Event {row['sample_id']} cannot map node1_seg_0002 to {event_domain}.")
        if event_domain != "P1_SOURCE":
            continue

        event_start = pd.Timestamp(str(row["event_start_local"]))
        event_end = pd.Timestamp(str(row["event_end_local"]))
        owned_start = min(member_times)
        owned_end = max(member_times)
        if event_start != owned_start or event_end != owned_end:
            raise ValueError(
                f"V6 event {row['sample_id']} violates episode-owned time lineage: "
                f"event=({event_start.isoformat()}, {event_end.isoformat()}), "
                f"owned=({owned_start.isoformat()}, {owned_end.isoformat()})."
            )
        if event_start > event_end:
            raise ValueError(f"V6 event {row['sample_id']} has event_start_local after event_end_local.")
        start_partition = fold_partition(event_start, spec)
        end_partition = fold_partition(event_end, spec)
        intersects_fold = not (event_end < spec.train_start or event_start >= spec.test_end)
        if not intersects_fold:
            continue
        if start_partition is None or end_partition is None or start_partition != end_partition:
            base_partition = "boundary_event"
            effective = "excluded"
            exclusion_reason = "boundary_event"
        elif str(row["label_status"]) != "LABELED" or not bool(row.get("intrinsic_eligibility", True)):
            base_partition = start_partition
            effective = "excluded"
            exclusion_reason = row.get("intrinsic_exclusion_reason", pd.NA)
        else:
            base_partition = start_partition
            effective = start_partition
            exclusion_reason = pd.NA
        if effective == "train" and event_start >= spec.train_end:
            raise ValueError(f"Event {row['sample_id']} starts after train_end but was assigned train.")
        if effective in {"train", "validation", "test"} and (start_partition != effective or end_partition != effective):
            raise ValueError(f"Event {row['sample_id']} assigned {effective} but start/end are not both inside that partition.")
        rows.append(
            {
                "sample_id": str(row["sample_id"]),
                "record_id": pd.NA,
                "view_id": "v6_event",
                "protocol_view_id": "v6_event",
                "fold_id": spec.fold_id,
                "deployment_domain": "P1_SOURCE",
                "base_partition": base_partition,
                "effective_partition": effective,
                "protocol_eligibility": effective != "excluded",
                "group_id": str(row["sample_id"]),
                "eligibility_status": "eligible" if effective != "excluded" else "excluded",
                "exclusion_reason": exclusion_reason,
                "purge_minutes": 0,
            }
        )
        if effective == "excluded" and exclusion_reason == "boundary_event":
            boundary_rows.append(
                {
                    "fold_id": spec.fold_id,
                    "sample_id": str(row["sample_id"]),
                    "deployment_domain": "P1_SOURCE",
                    "view_id": "v6_event",
                    "label_name": str(row["label_name"]),
                    "event_start_local": event_start.isoformat(),
                    "event_end_local": event_end.isoformat(),
                    "record_count": int(row["record_count"]),
                    "start_partition": start_partition,
                    "end_partition": end_partition,
                    "member_domain_values": json.dumps(member_domains, ensure_ascii=False, separators=(",", ":")),
                    "member_segment_values": json.dumps(member_segments, ensure_ascii=False, separators=(",", ":")),
                    "exclusion_reason": "boundary_event",
                }
            )
    return rows, boundary_rows


def build_fold_v6_block_assignments(
    v6_blocks: pd.DataFrame,
    spec,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    source_rows = v6_blocks.loc[v6_blocks["deployment_domain_name"].astype("string") == "P1_SOURCE"].copy()
    for row in source_rows.itertuples(index=False):
        partition = fold_partition(row.block_start_local, spec)
        if partition is None:
            continue
        effective = partition if str(row.label_status) == "LABELED" else "excluded"
        rows.append(
            {
                "sample_id": str(row.sample_id),
                "record_id": pd.NA,
                "view_id": "v6_b8_block",
                "protocol_view_id": "v6_b8_block",
                "fold_id": spec.fold_id,
                "deployment_domain": "P1_SOURCE",
                "base_partition": partition,
                "effective_partition": effective,
                "protocol_eligibility": effective != "excluded",
                "group_id": str(row.sample_id),
                "eligibility_status": "eligible" if effective != "excluded" else "excluded",
                "exclusion_reason": pd.NA if effective != "excluded" else row.intrinsic_exclusion_reason,
                "purge_minutes": 0,
            }
        )
    return rows


def boundary_event_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    columns = [
        "fold_id",
        "sample_id",
        "deployment_domain",
        "view_id",
        "label_name",
        "event_start_local",
        "event_end_local",
        "record_count",
        "start_partition",
        "end_partition",
        "member_domain_values",
        "member_segment_values",
        "exclusion_reason",
    ]
    if not rows:
        return pd.DataFrame(columns=columns).convert_dtypes()
    return pd.DataFrame(rows, columns=columns).convert_dtypes()


def build_v6_event_partition_counts(view_assignments: pd.DataFrame, v6_events: pd.DataFrame) -> pd.DataFrame:
    v6_assignment = view_assignments.loc[view_assignments["view_id"].astype("string") == "v6_event"].copy()
    if v6_assignment.empty:
        return pd.DataFrame(
            columns=["deployment_domain", "fold_id", "partition", "label_name", "exclusion_reason", "episode_count"]
        ).convert_dtypes()
    merged = v6_assignment.merge(
        v6_events.loc[:, ["sample_id", "label_name"]],
        on="sample_id",
        how="left",
        validate="many_to_one",
    )
    merged["partition"] = merged["effective_partition"].astype("string")
    grouped = (
        merged.groupby(
            ["deployment_domain", "fold_id", "partition", "label_name", "exclusion_reason"],
            dropna=False,
            sort=False,
        )
        .size()
        .reset_index(name="episode_count")
    )
    return grouped.convert_dtypes()


def assert_v6_event_partition_lineage(
    view_rows: list[dict[str, object]],
    v6_events: pd.DataFrame,
) -> None:
    assignment_frame = pd.DataFrame(view_rows).convert_dtypes()
    event_assignments = assignment_frame.loc[assignment_frame["view_id"].astype("string") == "v6_event"].copy()
    if event_assignments.empty:
        return
    if event_assignments.duplicated(subset=["sample_id", "fold_id"], keep=False).any():
        duplicates = event_assignments.loc[
            event_assignments.duplicated(subset=["sample_id", "fold_id"], keep=False),
            ["sample_id", "fold_id"],
        ]
        raise ValueError(f"V6 event assignments duplicate sample/fold pairs: {duplicates.to_dict(orient='records')}")
    event_domain_lookup = {
        str(row["sample_id"]): (
            "P1_SOURCE"
            if str(row["record.segment_id"]) == "node1_seg_0001"
            else "P2_TARGET"
            if str(row["record.segment_id"]) == "node1_seg_0002"
            else "UNKNOWN"
        )
        for row in v6_events.loc[:, ["sample_id", "record.segment_id"]].to_dict(orient="records")
    }
    event_assignments["expected_domain"] = event_assignments["sample_id"].astype("string").map(event_domain_lookup)
    mismatched = event_assignments.loc[
        event_assignments["deployment_domain"].astype("string") != event_assignments["expected_domain"].astype("string")
    ]
    if not mismatched.empty:
        raise ValueError(
            "V6 event domain assignment mismatch: "
            f"{mismatched.loc[:, ['sample_id', 'fold_id', 'deployment_domain', 'expected_domain']].to_dict(orient='records')}"
        )
