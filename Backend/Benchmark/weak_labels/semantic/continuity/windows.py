from __future__ import annotations

import math

import pandas as pd

from Backend.Benchmark.weak_labels.contracts.native import NativeContract, deterministic_id


def build_window_projections(frame: pd.DataFrame, point_assignments: pd.DataFrame, contract: NativeContract, operationalization: pd.Series) -> dict[str, pd.DataFrame]:
    merged = frame.merge(point_assignments[["sample_id", "assignment_id", "label"]], left_on="record.id", right_on="sample_id", how="left", validate="one_to_one")
    outputs: dict[str, pd.DataFrame] = {}
    for horizon in ("3h", "8h"):
        outputs[horizon] = _build_horizon(merged, horizon, contract, operationalization)
    return outputs


def _build_horizon(frame: pd.DataFrame, horizon: str, contract: NativeContract, operationalization: pd.Series) -> pd.DataFrame:
    window = contract.window_contracts
    hours = int(horizon[:-1])
    interval = _required_mapping(window, "window_interval")
    slot_formula = _required_mapping(window, "expected_slot_formula")
    slot_assignment = _required_mapping(window, "slot_assignment")
    coverage_contract = _required_mapping(window, "coverage")
    gap_contract = _required_mapping(window, "max_internal_gap")
    left_closed = str(_required_value(interval, "left_boundary")) == "CLOSED"
    right_closed = str(_required_value(interval, "right_boundary")) == "CLOSED"
    cadence = float(_required_value(window, "nominal_cadence_minutes"))
    expected_formula = str(_required_value(slot_formula, "formula"))
    include_anchor = bool(_required_value(window, "anchor_inclusion"))
    method = str(_required_value(slot_assignment, "method"))
    tolerance_value = slot_assignment.get("tolerance_minutes")
    tolerance = float(tolerance_value) if tolerance_value is not None else None
    min_coverage = float(_required_value(coverage_contract, "minimum_ratio"))
    max_gap = float(_required_value(gap_contract, "minutes"))
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
        timestamps = pd.to_datetime(candidates["sample_time_utc"], utc=True)
        if method == "NEAREST_NOMINAL_SLOT":
            if tolerance is None:
                raise ValueError("NEAREST_NOMINAL_SLOT requires tolerance_minutes.")
            elapsed_minutes = (timestamps - start).dt.total_seconds().div(60)
            candidates["_nominal_slot"] = (elapsed_minutes / cadence).round().astype("Int64")
            candidates["_slot_distance"] = (elapsed_minutes - candidates["_nominal_slot"].astype(float) * cadence).abs()
            candidates = candidates.loc[candidates["_slot_distance"] <= tolerance].copy()
            duplicate_slots = candidates.duplicated(["_nominal_slot"], keep=False).any() if not candidates.empty else False
        elif method == "OBSERVED_TIMESTAMP":
            # Coverage is based on unique valid observations.  Duplicate sample
            # timestamps remain a hard failure; they are not silently collapsed.
            duplicate_slots = timestamps.duplicated(keep=False).any() if not candidates.empty else False
        else:
            raise ValueError(f"Unsupported frozen window slot-assignment method: {method}")
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


def _required_mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Frozen window contract field {key!r} must be an object.")
    return value


def _required_value(payload: dict[str, object], key: str) -> object:
    if key not in payload or payload[key] is None:
        raise ValueError(f"Frozen window contract field {key!r} is missing.")
    return payload[key]
