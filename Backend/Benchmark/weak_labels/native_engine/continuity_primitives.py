from __future__ import annotations

import pandas as pd

from Backend.Benchmark.weak_labels.native_engine.contracts import NativeContract, deterministic_id


def build_continuity_primitives(frame: pd.DataFrame, contract: NativeContract) -> pd.DataFrame:
    working = frame.copy()
    working["sample_time_utc"] = pd.to_datetime(working["sample_time_utc"], errors="coerce", utc=True)
    working["time_integrity_ok"] = working["sample_time_utc"].notna()
    if working["record.id"].astype("string").duplicated().any():
        raise ValueError("record.id must be unique before continuity processing.")
    duplicate_time = working.duplicated(["record.segment_id", "sample_time_utc"], keep=False)
    if duplicate_time.any():
        raise ValueError("Duplicate sample timestamps within a segment require a frozen tie policy.")
    working = working.sort_values(["record.segment_id", "sample_time_utc", "record.id"], kind="stable").reset_index(drop=True)
    working["deployment_segment_id"] = working["record.segment_id"].astype("string")
    working["previous_record_id"] = working.groupby("deployment_segment_id", dropna=False)["record.id"].shift(1).astype("string")
    working["previous_sample_time_utc"] = working.groupby("deployment_segment_id", dropna=False)["sample_time_utc"].shift(1)
    working["delta_minutes_from_previous"] = (
        working["sample_time_utc"] - working["previous_sample_time_utc"]
    ).dt.total_seconds().div(60).astype("Float64")
    min_gap, max_gap = _strict_gap_bounds(contract)
    previous_valid = (
        working.groupby("deployment_segment_id", dropna=False)["time_integrity_ok"]
        .shift(1)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    strict_link = (
        working["time_integrity_ok"].fillna(False)
        & previous_valid.astype(bool)
        & working["delta_minutes_from_previous"].between(min_gap, max_gap, inclusive="both")
    )
    working["strictly_consecutive_from_previous"] = strict_link.astype("boolean")
    working["strict_break_reason"] = _break_reasons(working, strict_link)
    strict_index = (~strict_link).groupby(working["deployment_segment_id"], dropna=False).cumsum()
    working["strict_continuity_id"] = [
        deterministic_id(
            {
                "object_type": "STRICT_CONTINUITY",
                "schema_version": "native.strict-continuity.v1",
                "deployment_segment_id": str(segment),
                "chunk_index": int(index),
            }
        )
        for segment, index in zip(working["deployment_segment_id"], strict_index, strict=True)
    ]
    working["strict_previous_observation_available"] = strict_link.astype("boolean")
    working["feature_dependency_interval_start"] = working["sample_time_utc"]
    working["feature_dependency_interval_end"] = working["sample_time_utc"]
    working["persistence_dependency_interval_start"] = working["sample_time_utc"]
    working["persistence_dependency_interval_end"] = working["sample_time_utc"]
    return working


def _strict_gap_bounds(contract: NativeContract) -> tuple[float, float]:
    registry = contract.run_dir / "continuity" / "strict_continuity_contract.yaml"
    if not registry.exists():
        raise ValueError("Missing strict continuity contract.")
    import yaml

    payload = yaml.safe_load(registry.read_text(encoding="utf-8"))
    try:
        bounds = payload["allowed_gap_minutes"]
        return float(bounds[0]), float(bounds[1])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("Strict continuity contract must define allowed_gap_minutes.") from exc


def _break_reasons(frame: pd.DataFrame, strict_link: pd.Series) -> pd.Series:
    reasons = pd.Series(pd.NA, index=frame.index, dtype="string")
    reasons.loc[~frame["time_integrity_ok"].fillna(False)] = "TIME_INVALID"
    reasons.loc[frame["time_integrity_ok"].fillna(False) & frame["previous_record_id"].isna()] = "DEPLOYMENT_START"
    reasons.loc[
        frame["time_integrity_ok"].fillna(False)
        & frame["previous_record_id"].notna()
        & ~strict_link
    ] = "CADENCE_OR_MISSING_SLOT"
    return reasons


def build_continuity_registry(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "record.id", "environment_id", "deployment_segment_id", "strict_continuity_id",
        "previous_record_id", "sample_time_utc", "previous_sample_time_utc",
        "delta_minutes_from_previous", "strictly_consecutive_from_previous",
        "strict_break_reason",
    ]
    return frame.loc[:, [column for column in columns if column in frame.columns]].copy().convert_dtypes()
