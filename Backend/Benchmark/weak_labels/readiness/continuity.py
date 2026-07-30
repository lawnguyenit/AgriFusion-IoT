from __future__ import annotations

import numpy as np
import pandas as pd

from Backend.Benchmark.protocol_registry.contracts import ProtocolRegistry


STRICT_POLICY_ID = "STRICT_15M_PM2_V1"


def build_continuity_audit(
    e1_df: pd.DataFrame,
    *,
    min_gap_minutes: float,
    max_gap_minutes: float,
    window_horizons_hours: tuple[int, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = e1_df.sort_values(["deployment_id", "record.segment_id", "sample_time"], kind="stable").reset_index(drop=True)
    working["deployment_segment_id"] = (
        working["environment_id"].astype("string")
        + ":"
        + working["deployment_id"].astype("string")
        + ":"
        + working["record.segment_id"].astype("string")
    )
    segment_changed = (
        working["deployment_segment_id"].ne(working["deployment_segment_id"].shift()).fillna(True).astype(bool)
    )
    working["deployment_boundary_reason"] = pd.Series(
        ["SEGMENT_OR_DEPLOYMENT_START" if changed else "CONTINUOUS_DEPLOYMENT_SEGMENT" for changed in segment_changed],
        dtype="string",
    )
    working["delta_from_previous_min"] = (
        working.groupby("deployment_segment_id", sort=False)["sample_time"].diff().dt.total_seconds().div(60)
    )
    expected_minutes = pd.to_numeric(working["record.segment_expected_interval_sec"], errors="coerce").div(60)
    working["cadence_deviation_min"] = (working["delta_from_previous_min"] - expected_minutes).abs()
    missing_slots = pd.to_numeric(working["record.missing_slot_count"], errors="coerce").fillna(0)
    strictly_consecutive = (
        ~segment_changed
        & working["delta_from_previous_min"].between(min_gap_minutes, max_gap_minutes, inclusive="both")
        & missing_slots.eq(0)
    )
    working["strictly_consecutive_from_previous"] = strictly_consecutive.astype("boolean")
    working["strict_break_reason"] = _strict_break_reasons(
        segment_changed=segment_changed,
        delta_minutes=working["delta_from_previous_min"],
        missing_slots=missing_slots,
        min_gap_minutes=min_gap_minutes,
        max_gap_minutes=max_gap_minutes,
    )
    strict_break = ~strictly_consecutive
    working["_strict_group_number"] = strict_break.groupby(working["deployment_segment_id"]).cumsum().astype("Int64")
    working["strict_continuity_id"] = (
        working["deployment_segment_id"].astype("string")
        + ":strict_"
        + working["_strict_group_number"].astype("string").str.zfill(4)
    )
    working["strict_policy_candidate_id"] = STRICT_POLICY_ID
    working["moisture_delta_strict"] = working.groupby("strict_continuity_id", sort=False)[
        "npk.soil_moisture_pct"
    ].diff()
    working["ec_delta_abs_strict"] = (
        working.groupby("strict_continuity_id", sort=False)["npk.ec"].diff().abs()
    )
    window_metrics = _build_window_metrics(working, window_horizons_hours)
    return working.drop(columns=["_strict_group_number"]).convert_dtypes(), window_metrics


def attach_observed_low_runs(evidence_df: pd.DataFrame) -> pd.DataFrame:
    working = evidence_df.copy()
    low = working["low_flag"].fillna(False).astype(bool)
    run_break = (
        working["strict_continuity_id"]
        .astype("string")
        .ne(working["strict_continuity_id"].astype("string").shift())
        .fillna(True)
        | low.ne(low.shift(fill_value=False))
        | ~low
    )
    run_number = run_break.groupby(working["strict_continuity_id"]).cumsum()
    candidate_id = (
        working["strict_continuity_id"].astype("string")
        + ":low_run_"
        + run_number.astype("string").str.zfill(4)
    )
    working["observed_low_run_id"] = candidate_id.where(low, pd.NA).astype("string")
    working["observed_low_run_length_ending_at_anchor"] = (
        low.astype(int).groupby([working["strict_continuity_id"], run_number]).cumsum().where(low, 0).astype("Int64")
    )
    return working.convert_dtypes()


def build_causal_dependency_audit(
    evidence_df: pd.DataFrame,
    registry: ProtocolRegistry,
    *,
    window_horizons_hours: tuple[int, ...],
    persistence_candidates: tuple[int, ...],
) -> pd.DataFrame:
    complete_folds = registry.e1_fold_registry.loc[
        registry.e1_fold_registry["evaluation_usable"].fillna(False).astype(bool)
    ].copy()
    run_bounds = (
        evidence_df.dropna(subset=["observed_low_run_id"])
        .groupby("observed_low_run_id", as_index=False)
        .agg(observed_run_start=("sample_time", "min"), observed_run_end=("sample_time", "max"))
    )
    working = evidence_df.merge(run_bounds, on="observed_low_run_id", how="left")
    working["deployment_segment_start"] = working.groupby("deployment_segment_id", sort=False)[
        "sample_time"
    ].transform("min")
    for k_value in persistence_candidates:
        working[f"persistence_start_k{k_value}"] = working.groupby(
            "strict_continuity_id", sort=False
        )["sample_time"].shift(k_value - 1)
    projections: list[pd.DataFrame] = []
    for fold in complete_folds.to_dict(orient="records"):
        partitions = (
            ("train", pd.Timestamp(fold["train_start"]), pd.Timestamp(fold["train_end"])),
            ("validation", pd.Timestamp(fold["validation_start"]), pd.Timestamp(fold["validation_end"])),
            ("test", pd.Timestamp(fold["test_start"]), pd.Timestamp(fold["test_end"])),
        )
        for split_role, split_start, split_end in partitions:
            anchors = working.loc[
                working["sample_time"].ge(split_start) & working["sample_time"].lt(split_end)
            ].copy()
            for horizon in window_horizons_hours:
                feature_start = anchors["sample_time"] - pd.Timedelta(hours=horizon)
                for k_value in persistence_candidates:
                    persistence_start = anchors[f"persistence_start_k{k_value}"]
                    feature_crosses = feature_start.lt(split_start)
                    persistence_crosses = persistence_start.isna() | persistence_start.lt(split_start)
                    earliest = pd.concat([feature_start, persistence_start], axis=1).min(axis=1)
                    deployment_crosses = earliest.lt(anchors["deployment_segment_start"])
                    observed_run_crosses = anchors["observed_run_start"].notna() & (
                        anchors["observed_run_start"].lt(split_start)
                        | anchors["observed_run_end"].ge(split_end)
                    )
                    projected = pd.DataFrame(
                        {
                            "record_id": anchors["record.id"].astype("string"),
                            "fold_policy_id": fold["fold_policy_id"],
                            "fold_policy_role": fold["fold_policy_role"],
                            "fold_id": fold["fold_id"],
                            "split_role": split_role,
                            "window_horizon_hours": horizon,
                            "persistence_k": k_value,
                            "anchor_time": anchors["sample_time"],
                            "feature_dependency_start": feature_start,
                            "feature_dependency_end": anchors["sample_time"],
                            "persistence_dependency_start": persistence_start,
                            "persistence_dependency_end": anchors["sample_time"],
                            "feature_interval_crosses_split_or_purge": feature_crosses,
                            "persistence_interval_crosses_split_or_purge": persistence_crosses,
                            "dependency_crosses_deployment": deployment_crosses,
                            "observed_run_crosses_split": observed_run_crosses,
                            "observed_run_crossing_used_for_eligibility": False,
                            "evaluation_dependency_eligible": ~(
                                feature_crosses | persistence_crosses | deployment_crosses
                            ),
                        }
                    )
                    projected["evaluation_boundary_reason"] = [
                        _dependency_reason(feature, persistence, deployment)
                        for feature, persistence, deployment in zip(
                            feature_crosses, persistence_crosses, deployment_crosses
                        )
                    ]
                    projections.append(projected)
    return pd.concat(projections, ignore_index=True).convert_dtypes() if projections else pd.DataFrame()


def _build_window_metrics(working: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for deployment_segment_id, group in working.groupby("deployment_segment_id", sort=False):
        ordered = group.sort_values("sample_time", kind="stable")
        timestamp_series = ordered["sample_time"].reset_index(drop=True)
        timestamp_ns = timestamp_series.astype("int64").to_numpy()
        for horizon in horizons:
            expected_count = int(horizon * 4) + 1
            for position, row in enumerate(ordered.to_dict(orient="records")):
                anchor = pd.Timestamp(row["sample_time"])
                start = anchor - pd.Timedelta(hours=horizon)
                left = int(np.searchsorted(timestamp_ns, start.value, side="left"))
                window_ns = timestamp_ns[left : position + 1]
                gaps = np.diff(window_ns) / (60 * 1_000_000_000) if len(window_ns) > 1 else np.array([])
                valid_count = len(window_ns)
                rows.append(
                    {
                        "record_id": row["record.id"],
                        "deployment_segment_id": deployment_segment_id,
                        "window_horizon_hours": horizon,
                        "window_start": start,
                        "window_end": anchor,
                        "window_valid_observation_count": valid_count,
                        "window_expected_observation_count_15m": expected_count,
                        "window_coverage_ratio": min(valid_count / expected_count, 1.0),
                        "window_max_internal_gap_min": float(gaps.max()) if len(gaps) else pd.NA,
                        "window_missing_slot_count": max(expected_count - valid_count, 0),
                        "window_continuity_policy_status": "DIAGNOSTIC_ONLY_NOT_FROZEN",
                    }
                )
    return pd.DataFrame(rows).convert_dtypes()


def _strict_break_reasons(
    *,
    segment_changed: pd.Series,
    delta_minutes: pd.Series,
    missing_slots: pd.Series,
    min_gap_minutes: float,
    max_gap_minutes: float,
) -> pd.Series:
    reasons: list[str] = []
    for changed, delta, missing in zip(segment_changed, delta_minutes, missing_slots):
        if changed:
            reasons.append("DEPLOYMENT_OR_SEGMENT_BOUNDARY")
        elif missing > 0:
            reasons.append("MISSING_SLOT")
        elif pd.isna(delta):
            reasons.append("MISSING_DELTA")
        elif delta < min_gap_minutes:
            reasons.append("GAP_BELOW_STRICT_MIN")
        elif delta > max_gap_minutes:
            reasons.append("GAP_ABOVE_STRICT_MAX")
        else:
            reasons.append("STRICTLY_CONSECUTIVE")
    return pd.Series(reasons, dtype="string")


def _dependency_reason(feature_crosses: bool, persistence_crosses: bool, deployment_crosses: bool) -> str:
    reasons: list[str] = []
    if feature_crosses:
        reasons.append("FEATURE_INTERVAL_CROSSES_SPLIT_OR_PURGE")
    if persistence_crosses:
        reasons.append("PERSISTENCE_INTERVAL_UNAVAILABLE_OR_CROSSES_SPLIT_OR_PURGE")
    if deployment_crosses:
        reasons.append("DEPENDENCY_INTERVAL_CROSSES_DEPLOYMENT")
    return "|".join(reasons) if reasons else "CAUSAL_DEPENDENCY_INTERVALS_ADMISSIBLE"
