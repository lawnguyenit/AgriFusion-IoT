from __future__ import annotations

import pandas as pd


def build_boundary_audit(
    working: pd.DataFrame,
    runs: pd.DataFrame,
    folds: pd.DataFrame,
    q_id: str,
    threshold: float,
) -> pd.DataFrame:
    """Audit candidate runs crossing fold boundaries without moving them."""

    rows: list[dict[str, object]] = []
    for fold in folds.itertuples(index=False):
        fold_policy_id = str(fold.fold_policy_id)
        fold_id = str(fold.fold_id)
        boundaries = [
            ("validation_start", "train", "validation", getattr(fold, "validation_start")),
            ("test_start", "validation", "test", getattr(fold, "test_start")),
        ]
        for boundary_name, left_role, right_role, boundary in boundaries:
            boundary = pd.to_datetime(boundary, utc=True, errors="coerce")
            if pd.isna(boundary):
                continue
            crossed = runs.loc[
                (runs["start_time"] < boundary) & (runs["end_time"] >= boundary)
            ].copy()
            crossing_count = int(len(crossed))
            if crossed.empty:
                rows.append(
                    _empty_boundary_row(
                        q_id,
                        threshold,
                        fold_policy_id,
                        fold_id,
                        boundary_name,
                        left_role,
                        right_role,
                        boundary,
                    )
                )
                continue
            for event in crossed.itertuples(index=False):
                event_rows = working.loc[
                    working["observed_low_run_id"].eq(event.observed_low_run_id)
                ]
                left_count = int((event_rows["sample_time"] < boundary).sum())
                right_count = int((event_rows["sample_time"] >= boundary).sum())
                left_duration = _duration_minutes(
                    getattr(fold, f"{left_role}_start"), boundary
                )
                right_duration = _duration_minutes(
                    boundary, getattr(fold, f"{right_role}_end")
                )
                keep_left_shift = max(
                    0.0, (pd.Timestamp(event.end_time) - boundary).total_seconds() / 60.0
                )
                keep_right_shift = max(
                    0.0, (boundary - pd.Timestamp(event.start_time)).total_seconds() / 60.0
                )
                shift_pct = max(
                    _pct(keep_left_shift, left_duration),
                    _pct(keep_right_shift, right_duration),
                )
                rows.append(
                    {
                        "q_contract_id": q_id,
                        "threshold_value": threshold,
                        "fold_policy_id": fold_policy_id,
                        "fold_id": fold_id,
                        "boundary_name": boundary_name,
                        "left_split_role": left_role,
                        "right_split_role": right_role,
                        "boundary_time": boundary,
                        "observed_low_run_id": event.observed_low_run_id,
                        "event_start": event.start_time,
                        "event_end": event.end_time,
                        "event_observation_count": int(event.run_length),
                        "left_observation_count": left_count,
                        "right_observation_count": right_count,
                        "keep_event_left_shift_minutes": keep_left_shift,
                        "keep_event_right_shift_minutes": keep_right_shift,
                        "max_boundary_shift_percent": shift_pct,
                        "material_shift_ge_4_percent": bool(shift_pct >= 4.0),
                        "crossing_event_count": crossing_count,
                        "multi_split_event": False,
                        "boundary_review_status": (
                            "MATERIAL_SPLIT_CHANGE"
                            if shift_pct >= 4.0
                            else "REVIEW_REQUIRED"
                        ),
                        "authority_status": "CANDIDATE_ONLY",
                    }
                )
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(
            columns=[
                "q_contract_id",
                "threshold_value",
                "fold_policy_id",
                "fold_id",
                "boundary_name",
                "boundary_review_status",
            ]
        )
    event_boundary_counts = (
        result.loc[result["observed_low_run_id"].notna()]
        .groupby(["q_contract_id", "fold_policy_id", "fold_id", "observed_low_run_id"])[
            "boundary_name"
        ]
        .transform("nunique")
    )
    result.loc[result["observed_low_run_id"].notna(), "multi_split_event"] = (
        event_boundary_counts > 1
    ).to_numpy()
    return result


def _empty_boundary_row(
    q_id: str,
    threshold: float,
    fold_policy_id: str,
    fold_id: str,
    boundary_name: str,
    left_role: str,
    right_role: str,
    boundary: pd.Timestamp,
) -> dict[str, object]:
    return {
        "q_contract_id": q_id,
        "threshold_value": threshold,
        "fold_policy_id": fold_policy_id,
        "fold_id": fold_id,
        "boundary_name": boundary_name,
        "left_split_role": left_role,
        "right_split_role": right_role,
        "boundary_time": boundary,
        "observed_low_run_id": pd.NA,
        "event_start": pd.NaT,
        "event_end": pd.NaT,
        "event_observation_count": 0,
        "left_observation_count": 0,
        "right_observation_count": 0,
        "keep_event_left_shift_minutes": 0.0,
        "keep_event_right_shift_minutes": 0.0,
        "max_boundary_shift_percent": 0.0,
        "material_shift_ge_4_percent": False,
        "crossing_event_count": 0,
        "multi_split_event": False,
        "boundary_review_status": "NO_CROSSING_EVENT",
        "authority_status": "CANDIDATE_ONLY",
    }


def _duration_minutes(start: object, end: object) -> float:
    start_ts = pd.to_datetime(start, utc=True, errors="coerce")
    end_ts = pd.to_datetime(end, utc=True, errors="coerce")
    if pd.isna(start_ts) or pd.isna(end_ts):
        return 0.0
    return max(0.0, (end_ts - start_ts).total_seconds() / 60.0)


def _pct(value: float, denominator: float) -> float:
    return 0.0 if denominator <= 0 else value / denominator * 100.0
