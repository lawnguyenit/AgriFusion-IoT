from __future__ import annotations

import json

import pandas as pd


def build_environment_eligibility_matrix(view_observation_registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, group in view_observation_registry.groupby(
        ["environment_id", "environment_stage_name", "view_id", "target_label"],
        dropna=False,
        sort=False,
    ):
        environment_id, stage_name, view_id, target_label = keys
        target_frame = group.copy()
        base_row_count = int(len(target_frame))
        eligible_mask = target_frame["view_eligible"].fillna(False).astype(bool)
        eligible_row_count = int(eligible_mask.sum())
        excluded_frame = target_frame.loc[~eligible_mask].copy()
        exclusion_reason_counts = (
            excluded_frame["view_exclusion_reason"].astype("string").fillna("<NA>").value_counts(sort=False).to_dict()
            if not excluded_frame.empty
            else {}
        )
        rows.append(
            {
                "environment_id": environment_id,
                "stage_name": stage_name,
                "view_id": view_id,
                "target_label": target_label,
                "base_row_count": base_row_count,
                "eligible_row_count": eligible_row_count,
                "excluded_row_count": int(base_row_count - eligible_row_count),
                "eligible_rate": float(eligible_row_count / base_row_count) if base_row_count > 0 else pd.NA,
                "technical_invalid_excluded_count": int(
                    (
                        ~target_frame["technical_valid"].fillna(False).astype(bool)
                        & ~eligible_mask
                    ).sum()
                ),
                "insufficient_history_excluded_count": int(
                    excluded_frame["view_exclusion_reason"].astype("string").str.contains("insufficient_history", na=False).sum()
                )
                if not excluded_frame.empty
                else 0,
                "window_ineligible_excluded_count": int(
                    excluded_frame["view_label_status"].astype("string").str.contains("EXCLUDED_WINDOW_INELIGIBLE", na=False).sum()
                )
                if not excluded_frame.empty
                else 0,
                "missing_slot_affected_count": int(
                    (excluded_frame["missing_slot_count"].fillna(0).astype(int) > 0).sum()
                )
                if not excluded_frame.empty
                else 0,
                "buffered_or_replayed_count": int(
                    (excluded_frame["buffered"].fillna(False).astype(bool) | excluded_frame["replayed"].fillna(False).astype(bool)).sum()
                )
                if not excluded_frame.empty
                else 0,
                "exclusion_reason_counts_json": json.dumps(
                    {str(reason): int(count) for reason, count in exclusion_reason_counts.items()},
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_environment_continuity_matrix(observation_registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, group in observation_registry.groupby(
        ["environment_id", "environment_stage_name", "day_id", "segment_id"],
        dropna=False,
        sort=False,
    ):
        environment_id, stage_name, day_id, segment_id = keys
        continuity_counts = group["continuity_status"].astype("string").value_counts(sort=False).to_dict()
        rows.append(
            {
                "environment_id": environment_id,
                "stage_name": stage_name,
                "day_id": day_id,
                "segment_id": segment_id,
                "row_count": int(len(group)),
                "technical_invalid_row_count": int((~group["technical_valid"].fillna(False).astype(bool)).sum()),
                "gap_row_count": int(group["gap_flag"].fillna(False).astype(bool).sum()),
                "gap_rate": float(group["gap_flag"].fillna(False).astype(bool).mean()) if not group.empty else pd.NA,
                "replayed_row_count": int(group["replayed"].fillna(False).astype(bool).sum()),
                "buffered_row_count": int(group["buffered"].fillna(False).astype(bool).sum()),
                "avg_missing_slot_count": float(pd.to_numeric(group["missing_slot_count"], errors="coerce").fillna(0).mean()) if not group.empty else pd.NA,
                "max_missing_slot_count": int(pd.to_numeric(group["missing_slot_count"], errors="coerce").fillna(0).max()) if not group.empty else 0,
                "continuity_status_counts_json": json.dumps(
                    {str(status): int(count) for status, count in continuity_counts.items()},
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()
