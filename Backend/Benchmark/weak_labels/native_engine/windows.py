from __future__ import annotations

import math

import pandas as pd

from Backend.Benchmark.weak_labels.native_engine.contracts import NativeContract, deterministic_id


def build_window_projections(frame: pd.DataFrame, point_assignments: pd.DataFrame, contract: NativeContract, operationalization: pd.Series) -> dict[str, pd.DataFrame]:
    merged = frame.merge(point_assignments[["sample_id", "assignment_id", "label"]], left_on="record.id", right_on="sample_id", how="left", validate="one_to_one")
    outputs: dict[str, pd.DataFrame] = {}
    for horizon in ("3h", "8h"):
        outputs[horizon] = _build_horizon(merged, horizon, contract, operationalization)
    return outputs


def _build_horizon(frame: pd.DataFrame, horizon: str, contract: NativeContract, operationalization: pd.Series) -> pd.DataFrame:
    window = contract.window_contracts
    hours = int(horizon[:-1])
    left_closed = str(window["window_interval"].get("left_boundary", "CLOSED")) == "CLOSED"
    right_closed = str(window["window_interval"].get("right_boundary", "CLOSED")) == "CLOSED"
    cadence = float(window["nominal_cadence_minutes"])
    expected_formula = str(window["expected_slot_formula"].get("formula", "NOMINAL_SLOTS_PLUS_ANCHOR"))
    include_anchor = bool(window["anchor_inclusion"])
    tolerance = float(window["slot_assignment"].get("tolerance_minutes", 2.0))
    min_coverage = float(window["coverage"].get("minimum_ratio", window["coverage"].get("ratio", 0.75)))
    max_gap = float(window["max_internal_gap"].get("minutes", 30.0))
    rows: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        anchor = pd.Timestamp(record["sample_time_utc"])
        start = anchor - pd.Timedelta(hours=hours)
        candidates = frame.loc[frame["deployment_segment_id"].astype("string") == str(record["deployment_segment_id"])].copy()
        timestamps = pd.to_datetime(candidates["sample_time_utc"], utc=True)
        lower = timestamps >= start if left_closed else timestamps > start
        upper = timestamps <= anchor if right_closed else timestamps < anchor
        if not include_anchor:
            upper &= timestamps < anchor
        candidates = candidates.loc[lower & upper].copy()
        elapsed_minutes = (pd.to_datetime(candidates["sample_time_utc"], utc=True) - start).dt.total_seconds().div(60)
        candidates["_nominal_slot"] = (elapsed_minutes / cadence).round().astype("Int64")
        candidates["_slot_distance"] = (elapsed_minutes - candidates["_nominal_slot"].astype(float) * cadence).abs()
        candidates = candidates.loc[candidates["_slot_distance"] <= tolerance].copy()
        duplicate_slots = candidates.duplicated(["_nominal_slot"], keep=False).any() if not candidates.empty else False
        if duplicate_slots:
            accepted = pd.DataFrame()
        else:
            accepted = candidates
        expected_slots = _expected_slots(hours, cadence, expected_formula, include_anchor)
        observed_slots = int(len(accepted))
        coverage = float(observed_slots / expected_slots) if expected_slots else 0.0
        max_observed_gap = _max_gap(accepted)
        eligible = bool(
            not duplicate_slots
            and coverage >= min_coverage
            and (math.isnan(max_observed_gap) or max_observed_gap <= max_gap)
            and observed_slots > 0
        )
        dependency_start = start if eligible else anchor
        projection_id = deterministic_id(
            {
                "object_type": "WINDOW_PROJECTION",
                "schema_version": "native.window-projection.v1",
                "semantic_contract_hash": contract.semantic_contract_hash,
                "operationalization_id": str(operationalization["operationalization_id"]),
                "task_id": "TEMPORAL_ANCHOR",
                "horizon_id": horizon,
                "sample_id": str(record["record.id"]),
            }
        )
        rows.append(
            {
                "window_projection_id": projection_id,
                "sample_id": str(record["record.id"]),
                "horizon_id": horizon,
                "window_start_utc": start,
                "window_end_utc": anchor,
                "window_valid_observation_count": observed_slots,
                "window_expected_slot_count": expected_slots,
                "window_coverage_ratio": coverage,
                "window_max_internal_gap_minutes": max_observed_gap,
                "window_duplicate_slot": bool(duplicate_slots),
                "representation_history_status": "ELIGIBLE" if eligible else "INELIGIBLE",
                "temporal_window_dependency_admissible": eligible,
                "dependency_interval_start": dependency_start,
                "dependency_interval_end": anchor,
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _expected_slots(hours: int, cadence: float, formula: str, include_anchor: bool) -> int:
    base = int(round(hours * 60 / cadence))
    if formula == "NOMINAL_SLOTS_PLUS_ANCHOR" or include_anchor:
        return base + 1
    return base


def _max_gap(frame: pd.DataFrame) -> float:
    if len(frame) < 2:
        return float("nan")
    times = pd.to_datetime(frame["sample_time_utc"], utc=True).sort_values()
    return float(times.diff().dt.total_seconds().div(60).max())
