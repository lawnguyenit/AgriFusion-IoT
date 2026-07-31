from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from Backend.Benchmark.shared.split_policy import build_split_manifest, build_split_plan
from Backend.Benchmark.weak_labels.infrastructure.shared.configs import SUPPORTED_RUN_PROFILES


@dataclass(frozen=True)
class BaseSplitBundle:
    ordered_df: pd.DataFrame
    assignments_df: pd.DataFrame
    split_manifest: dict[str, object]
    boundary_timestamps: dict[str, int]


def build_base_split_bundle(
    canonical_df: pd.DataFrame,
    *,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    base_split_strategy: str,
    run_profile: str,
) -> BaseSplitBundle:
    if run_profile not in SUPPORTED_RUN_PROFILES:
        raise ValueError(f"Unsupported weak-label run_profile: {run_profile}")
    ordered = canonical_df.copy()
    ordered["record.ts_sample"] = pd.to_numeric(ordered["record.ts_sample"], errors="coerce")
    ordered = ordered.dropna(subset=["record.ts_sample"]).copy()
    ordered["record.ts_sample"] = ordered["record.ts_sample"].astype("int64")
    ordered = ordered.sort_values(["record.ts_sample", "record.node_id", "record.id"], kind="stable").reset_index(drop=True)

    if run_profile == "segment_holdout_last":
        return _build_segment_holdout_bundle(
            ordered,
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
        )

    split_plan = build_split_plan(
        row_count=len(ordered),
        train_ratio=train_ratio,
        validation_ratio=validation_ratio,
        test_ratio=test_ratio,
        strategy_name=base_split_strategy,
        timestamps=ordered["record.ts_sample"].tolist(),
    )
    assignments = _assign_partitions_from_plan(ordered, split_plan)
    manifest = build_split_manifest(
        dataframe=ordered.rename(columns={"record.ts_sample": "timestamp"}),
        split_plan=split_plan,
        timestamp_column="timestamp",
    )
    return BaseSplitBundle(
        ordered_df=ordered,
        assignments_df=assignments,
        split_manifest=manifest,
        boundary_timestamps=_extract_boundary_timestamps(assignments),
    )


def _build_segment_holdout_bundle(
    ordered: pd.DataFrame,
    *,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
) -> BaseSplitBundle:
    if "record.segment_id" not in ordered.columns:
        raise ValueError("segment_holdout_last requires 'record.segment_id'.")
    segment_ids = ordered["record.segment_id"].dropna().astype("string").drop_duplicates().tolist()
    if len(segment_ids) < 2:
        raise ValueError("segment_holdout_last requires at least two Layer1 segments.")
    test_segment_id = str(segment_ids[-1])
    pretest = ordered.loc[ordered["record.segment_id"].astype("string") != test_segment_id].copy().reset_index(drop=True)
    test_rows = ordered.loc[ordered["record.segment_id"].astype("string") == test_segment_id].copy().reset_index(drop=True)
    if pretest.empty or test_rows.empty:
        raise ValueError("segment_holdout_last requires both pre-test and test segment rows.")

    pretest_plan = build_split_plan(
        row_count=len(pretest),
        train_ratio=(train_ratio / max(train_ratio + validation_ratio, 1e-9)),
        validation_ratio=(validation_ratio / max(train_ratio + validation_ratio, 1e-9)),
        test_ratio=0.0,
        strategy_name="chronological_v1",
        timestamps=pretest["record.ts_sample"].tolist(),
    )
    assignments = []
    pretest_assignments = _assign_partitions_from_plan(pretest, pretest_plan)
    pretest_assignments.loc[pretest_assignments["base_partition"] == "test", "base_partition"] = "validation"
    assignments.append(pretest_assignments)
    test_assignments = pd.DataFrame(
        {
            "record.id": test_rows["record.id"].astype("string"),
            "record.ts_sample": test_rows["record.ts_sample"].astype("int64"),
            "base_partition": pd.Series(["test"] * len(test_rows), dtype="string"),
            "split.boundary_before": pd.Series([False] * len(test_rows), dtype="boolean"),
            "base_partition_index": range(len(test_rows)),
        }
    )
    if len(test_assignments):
        test_assignments.loc[test_assignments.index[0], "split.boundary_before"] = True
    assignments.append(test_assignments)
    all_assignments = pd.concat(assignments, ignore_index=True)
    ordered_assignments = ordered[["record.id", "record.ts_sample"]].merge(
        all_assignments,
        on=["record.id", "record.ts_sample"],
        how="left",
        validate="one_to_one",
    )
    manifest = {
        "strategy_name": "segment_holdout_last",
        "row_count": int(len(ordered)),
        "train_ratio": train_ratio,
        "validation_ratio": validation_ratio,
        "test_ratio": test_ratio,
        "notes": "Train/validation on all but the last Layer1 segment; test on the last Layer1 segment.",
        "segments": [{"name": partition, "row_count": int((ordered_assignments["base_partition"] == partition).sum())} for partition in ("train", "validation", "test")],
    }
    return BaseSplitBundle(
        ordered_df=ordered,
        assignments_df=ordered_assignments,
        split_manifest=manifest,
        boundary_timestamps=_extract_boundary_timestamps(ordered_assignments),
    )


def _assign_partitions_from_plan(ordered: pd.DataFrame, split_plan) -> pd.DataFrame:
    assignments = pd.DataFrame(
        {
            "record.id": ordered["record.id"].astype("string"),
            "record.ts_sample": ordered["record.ts_sample"].astype("int64"),
            "base_partition": pd.Series(["excluded"] * len(ordered), dtype="string"),
            "split.boundary_before": pd.Series([False] * len(ordered), dtype="boolean"),
            "base_partition_index": range(len(ordered)),
        }
    )
    for segment in split_plan.segments:
        assignments.loc[segment.start : segment.stop - 1, "base_partition"] = segment.name
        if segment.start < len(assignments):
            assignments.loc[segment.start, "split.boundary_before"] = True
    return assignments


def _extract_boundary_timestamps(assignments_df: pd.DataFrame) -> dict[str, int]:
    boundaries: dict[str, int] = {}
    for partition in ("validation", "test"):
        partition_rows = assignments_df.loc[assignments_df["base_partition"] == partition]
        if partition_rows.empty:
            continue
        boundaries[partition] = int(partition_rows["record.ts_sample"].iloc[0])
    return boundaries
