from __future__ import annotations

from dataclasses import dataclass
import json

import pandas as pd

from Backend.Benchmark.weak_labels.shared.configs import LABEL_STATUS_LABELED, POINT_LABELS, V6_EVENT_LABELS
from Backend.Benchmark.weak_labels.shared.helpers import local_time_bucket


@dataclass(frozen=True)
class V6NormalAuditArtifacts:
    candidate_audit: pd.DataFrame
    selection_audit: pd.DataFrame


def build_normal_candidate_and_selection_audits(
    *,
    raw_event_df: pd.DataFrame,
    event_labels: pd.DataFrame,
    domain_by_segment: dict[str, str],
) -> V6NormalAuditArtifacts:
    candidate_rows, membership_rows = _build_normal_candidate_rows(raw_event_df, domain_by_segment)
    candidate_df = pd.DataFrame(candidate_rows).convert_dtypes()
    membership_df = pd.DataFrame(membership_rows).convert_dtypes()
    selected_events = event_labels.loc[
        (event_labels["label_name"].astype("string") == V6_EVENT_LABELS[0])
        & (event_labels["matched_to_event_id"].astype("string") != "<NA>")
    ].copy()
    selected_events = selected_events.convert_dtypes()

    record_to_candidate = membership_df.set_index("record.id")["candidate_episode_id"].astype("string").to_dict() if not membership_df.empty else {}
    selection_rows: list[dict[str, object]] = []
    candidate_updates: dict[str, dict[str, object]] = {}
    for row in selected_events.to_dict(orient="records"):
        record_ids = _json_list(row["record_ids"])
        candidate_ids = sorted({record_to_candidate.get(record_id, "<MISSING>") for record_id in record_ids})
        exact_candidate_match = False
        if len(candidate_ids) == 1 and candidate_ids[0] != "<MISSING>":
            candidate_record_ids = set(
                membership_df.loc[
                    membership_df["candidate_episode_id"].astype("string") == candidate_ids[0],
                    "record.id",
                ].astype("string").tolist()
            )
            exact_candidate_match = candidate_record_ids == set(record_ids)
        selection_issue = (
            "selected_rows_span_multiple_candidates"
            if len(candidate_ids) > 1
            else "selected_rows_do_not_exactly_match_candidate"
            if candidate_ids and candidate_ids[0] != "<MISSING>" and not exact_candidate_match
            else pd.NA
        )
        selection_rows.append(
            {
                "selected_episode_id": str(row["sample_id"]),
                "matched_to_event_id": str(row["matched_to_event_id"]),
                "deployment_domain": domain_by_segment.get(str(row["record.segment_id"]), "UNKNOWN"),
                "selected_start_local": str(row["event_start_local"]),
                "selected_end_local": str(row["event_end_local"]),
                "selected_row_count": int(row["record_count"]),
                "source_candidate_count": int(len(candidate_ids)),
                "source_candidate_ids": json.dumps(candidate_ids, ensure_ascii=False, separators=(",", ":")),
                "exact_candidate_match": bool(exact_candidate_match),
                "matching_criteria": "same_segment|same_time_of_day_band|global_head_selection",
                "selection_issue": selection_issue,
            }
        )
        for candidate_id in candidate_ids:
            if candidate_id == "<MISSING>":
                continue
            update = candidate_updates.setdefault(
                candidate_id,
                {
                    "selected_for_training": True,
                    "matched_to_event_ids": [],
                    "selection_event_ids": [],
                    "selection_issue_values": [],
                },
            )
            update["matched_to_event_ids"].append(str(row["matched_to_event_id"]))
            update["selection_event_ids"].append(str(row["sample_id"]))
            if pd.notna(selection_issue):
                update["selection_issue_values"].append(str(selection_issue))

    if not candidate_df.empty:
        selected_for_training: list[bool] = []
        matched_to_event_ids: list[object] = []
        matching_criteria: list[object] = []
        rejection_reason: list[object] = []
        for row in candidate_df.itertuples(index=False):
            update = candidate_updates.get(str(row.episode_id))
            if update is None:
                selected_for_training.append(False)
                matched_to_event_ids.append(pd.NA)
                matching_criteria.append(pd.NA)
                rejection_reason.append("not_selected_by_current_matching_strategy")
                continue
            selected_for_training.append(True)
            matched_to_event_ids.append("|".join(update["matched_to_event_ids"]))
            matching_criteria.append("same_segment|same_time_of_day_band|global_head_selection")
            rejection_reason.append("|".join(update["selection_issue_values"]) if update["selection_issue_values"] else pd.NA)
        candidate_df["selected_for_training"] = pd.Series(selected_for_training, dtype="boolean")
        candidate_df["matched_to_event_id"] = pd.Series(matched_to_event_ids, dtype="string")
        candidate_df["matching_criteria"] = pd.Series(matching_criteria, dtype="string")
        candidate_df["rejection_reason"] = pd.Series(rejection_reason, dtype="string")
    return V6NormalAuditArtifacts(
        candidate_audit=candidate_df.convert_dtypes(),
        selection_audit=pd.DataFrame(selection_rows).convert_dtypes(),
    )


def _build_normal_candidate_rows(
    raw_event_df: pd.DataFrame,
    domain_by_segment: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    memberships: list[dict[str, object]] = []
    ordered = raw_event_df.sort_values(["record.ts_sample", "record.id"], kind="stable").reset_index(drop=True)
    active_group: list[pd.Series] = []
    candidate_index = 0

    def flush() -> None:
        nonlocal candidate_index, active_group
        if not active_group:
            return
        candidate_index += 1
        candidate_id = f"v6_norm_cand_{candidate_index:05d}"
        frame = pd.DataFrame(active_group).convert_dtypes()
        start_local = pd.Timestamp(frame["timestamp_local"].iloc[0])
        end_local = pd.Timestamp(frame["timestamp_local"].iloc[-1])
        cadence_sec = int(round(float(pd.to_numeric(frame["record.segment_expected_interval_sec"], errors="coerce").dropna().iloc[0])))
        expected_slots = max(int(round(((end_local - start_local).total_seconds() / max(cadence_sec, 1)))) + 1, 1)
        coverage = float(len(frame) / expected_slots)
        iso = start_local.isocalendar()
        rows.append(
            {
                "episode_id": candidate_id,
                "start_local": start_local.isoformat(),
                "end_local": end_local.isoformat(),
                "duration_hours": float((end_local - start_local).total_seconds() / 3600.0),
                "row_count": int(len(frame)),
                "coverage_ratio": coverage,
                "deployment_domain": domain_by_segment.get(str(frame["record.segment_id"].iloc[0]), "UNKNOWN"),
                "record.segment_id": str(frame["record.segment_id"].iloc[0]),
                "calendar_day": start_local.strftime("%Y-%m-%d"),
                "calendar_week": f"{iso.year}-W{int(iso.week):02d}",
                "time_of_day_band": local_time_bucket(start_local),
            }
        )
        memberships.extend(
            {
                "record.id": record_id,
                "candidate_episode_id": candidate_id,
            }
            for record_id in frame["record.id"].astype("string").tolist()
        )
        active_group = []

    for _, row in ordered.iterrows():
        is_labeled = str(row.get("point_label_status", "")) == LABEL_STATUS_LABELED
        is_normal = str(row.get("point_train_label_name", "")) == POINT_LABELS[0]
        if not is_labeled or not is_normal:
            flush()
            continue
        if active_group:
            previous = active_group[-1]
            if str(previous.get("raw_continuity_chunk_id")) != str(row.get("raw_continuity_chunk_id")):
                flush()
        active_group.append(row)
    flush()
    return rows, memberships


def _json_list(payload: object) -> list[str]:
    if payload is None or payload is pd.NA:
        return []
    if isinstance(payload, list):
        return [str(item) for item in payload]
    return [str(item) for item in json.loads(str(payload))]
