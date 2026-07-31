from __future__ import annotations

import pandas as pd

from Backend.Benchmark.weak_labels.contracts.native import NativeContract, deterministic_id


def build_observed_low_runs(frame: pd.DataFrame, point_assignments: pd.DataFrame, contract: NativeContract, operationalization: pd.Series) -> pd.DataFrame:
    working = frame.merge(
        point_assignments[["sample_id", "label", "assignment_id"]],
        left_on="record.id",
        right_on="sample_id",
        how="left",
        validate="one_to_one",
    ).sort_values(["deployment_segment_id", "sample_time_utc", "record.id"], kind="stable")
    working["previous_label"] = working.groupby("deployment_segment_id", dropna=False)["label"].shift(1)
    run_ids: list[object] = []
    support_depths: list[int] = []
    starts: dict[str, dict[str, object]] = {}
    current_key: tuple[str, str] | None = None
    current_depth = 0
    for row in working.to_dict(orient="records"):
        segment = str(row["deployment_segment_id"])
        label = str(row.get("label", ""))
        strict = bool(row.get("strictly_consecutive_from_previous", False))
        previous_label = str(row.get("previous_label", ""))
        if label == "low_relative_moisture_point" and strict and current_key is not None and current_key[0] == segment and previous_label == "low_relative_moisture_point":
            current_depth += 1
        elif label == "low_relative_moisture_point":
            current_depth = 1
            run_start = str(row["record.id"])
            current_key = (segment, run_start)
            starts[str(current_key)] = {
                "run_start_record_id": run_start,
                "deployment_segment_id": segment,
                "run_start_time_utc": row["sample_time_utc"],
            }
        else:
            current_key = None
            current_depth = 0
        run_id = pd.NA
        if current_key is not None:
            run_id = deterministic_id(
                {
                    "object_type": "OBSERVED_LOW_RUN",
                    "schema_version": "native.observed-low-run.v1",
                    "semantic_contract_hash": contract.semantic_contract_hash,
                    "operationalization_id": str(operationalization["operationalization_id"]),
                    "deployment_segment_id": current_key[0],
                    "run_start_record_id": current_key[1],
                }
            )
        run_ids.append(run_id)
        support_depths.append(current_depth)
    working["observed_low_run_id"] = pd.Series(run_ids, index=working.index, dtype="string")
    working["support_depth_at_anchor"] = pd.Series(support_depths, index=working.index, dtype="Int64")
    working["elapsed_low_duration_min"] = _elapsed_duration(working)
    return working.sort_index().loc[:, ["record.id", "observed_low_run_id", "support_depth_at_anchor", "elapsed_low_duration_min"]].convert_dtypes()


def _elapsed_duration(frame: pd.DataFrame) -> pd.Series:
    grouped = frame.groupby("observed_low_run_id", dropna=False)["sample_time_utc"]
    starts = grouped.transform("min")
    elapsed = (frame["sample_time_utc"] - starts).dt.total_seconds().div(60)
    return elapsed.where(frame["observed_low_run_id"].notna())
