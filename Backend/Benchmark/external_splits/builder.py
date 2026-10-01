from __future__ import annotations

import pandas as pd


PARTITIONS = ("train", "validation", "test")


def assign_timestamp_blocks(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
    train_ratio: float,
    validation_ratio: float,
    test_ratio: float,
    shared_timestamp_columns: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, dict[str, object]]:
    ratios = (train_ratio, validation_ratio, test_ratio)
    if any(value <= 0 for value in ratios) or abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("Split ratios must be positive and sum to 1.")
    required = {"sample_id", timestamp_column, *shared_timestamp_columns}
    if not required.issubset(frame.columns):
        raise ValueError("Split input must include sample_id and the declared timestamp column.")
    if frame["sample_id"].astype("string").duplicated().any():
        raise ValueError("Split input sample_id values must be unique.")
    timestamps = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ValueError("Split input timestamps must all be valid.")
    linked_columns = (timestamp_column, *shared_timestamp_columns)
    missing_linked = [column for column in linked_columns if column not in frame]
    if missing_linked:
        raise ValueError(f"Shared timestamp columns are absent: {missing_linked}")
    parent = list(range(len(frame)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    key_owner: dict[pd.Timestamp, int] = {}
    for column in linked_columns:
        linked = pd.to_datetime(frame[column], errors="coerce", utc=True)
        for index, value in enumerate(linked):
            if pd.isna(value):
                continue
            previous = key_owner.setdefault(value, index)
            union(index, previous)
    roots = [find(index) for index in range(len(frame))]
    block_frame = pd.DataFrame({"root": roots, "anchor_time": timestamps})
    blocks = (
        block_frame.groupby("root", sort=False)
        .agg(block_start=("anchor_time", "min"), block_end=("anchor_time", "max"), row_count=("anchor_time", "size"))
        .sort_values(["block_start", "block_end", "root"], kind="stable")
        .reset_index()
    )
    if len(blocks) < 3:
        raise ValueError("At least three distinct linked timestamp blocks are required for three partitions.")
    train_end = max(1, int(len(blocks) * train_ratio))
    validation_end = max(train_end + 1, int(len(blocks) * (train_ratio + validation_ratio)))
    validation_end = min(validation_end, len(blocks) - 1)
    partition_by_root = {
        int(row.root): "train" if index < train_end else "validation" if index < validation_end else "test"
        for index, row in enumerate(blocks.itertuples(index=False))
    }
    partition_by_row = [partition_by_root[root] for root in roots]
    block_id_by_root = {int(row.root): f"time_block_{index + 1:06d}" for index, row in enumerate(blocks.itertuples(index=False))}
    block_id_by_row = [block_id_by_root[root] for root in roots]
    output = pd.DataFrame(
        {
            "sample_id": frame["sample_id"].astype("string"),
            "timestamp_utc": timestamps,
            "partition": pd.Series(partition_by_row, dtype="string"),
        }
    )
    output["timestamp_block_id"] = pd.Series(block_id_by_row, dtype="string")
    output["fold_id"] = "external_temporal_70_15_15"
    summary: dict[str, object] = {
        "policy_id": "EXTERNAL_GLOBAL_TIMESTAMP_BLOCK_70_15_15_V1",
        "assignment_unit": f"linked UTC timestamp keys {list(linked_columns)}; rows sharing any key stay in one block",
        "ratios_by_unique_timestamp": {"train": train_ratio, "validation": validation_ratio, "test": test_ratio},
        "timestamp_block_count": int(len(blocks)),
        "unique_anchor_timestamp_count": int(timestamps.nunique()),
        "shared_timestamp_columns": list(shared_timestamp_columns),
        "timestamp_boundaries": {
            "train_end_exclusive": blocks.loc[train_end, "block_start"].isoformat(),
            "validation_end_exclusive": blocks.loc[validation_end, "block_start"].isoformat(),
        },
        "partition_summary": {
            name: {
                "rows": int(output["partition"].eq(name).sum()),
                "unique_timestamps": int(output.loc[output["partition"].eq(name), "timestamp_utc"].nunique()),
                "timestamp_blocks": int(output.loc[output["partition"].eq(name), "timestamp_block_id"].nunique()),
                "start": output.loc[output["partition"].eq(name), "timestamp_utc"].min().isoformat(),
                "end": output.loc[output["partition"].eq(name), "timestamp_utc"].max().isoformat(),
            }
            for name in PARTITIONS
        },
    }
    return output, summary
