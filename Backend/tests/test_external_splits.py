from __future__ import annotations

import unittest

import pandas as pd

from Backend.Benchmark.external_splits.builder import assign_timestamp_blocks


class ExternalTimestampSplitTests(unittest.TestCase):
    def test_same_timestamp_rows_are_assigned_jointly_to_chronological_partitions(self) -> None:
        times = pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC")
        frame = pd.DataFrame(
            {
                "sample_id": [f"s{i}" for i in range(40)],
                "timestamp": list(times) * 2,
                "entity_id": ["line_1"] * 20 + ["line_2"] * 20,
            }
        )
        splits, summary = assign_timestamp_blocks(
            frame,
            timestamp_column="timestamp",
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
        )
        self.assertEqual(splits.groupby("timestamp_utc")["partition"].nunique().max(), 1)
        self.assertEqual(summary["partition_summary"]["train"]["unique_timestamps"], 14)
        self.assertEqual(summary["partition_summary"]["validation"]["unique_timestamps"], 3)
        self.assertEqual(summary["partition_summary"]["test"]["unique_timestamps"], 3)
        self.assertEqual(splits.loc[0, "partition"], "train")
        self.assertEqual(splits.loc[len(splits) - 1, "partition"], "test")

    def test_invalid_split_ratio_is_rejected(self) -> None:
        frame = pd.DataFrame({"sample_id": ["a", "b", "c"], "timestamp": pd.date_range("2024-01-01", periods=3)})
        with self.assertRaisesRegex(ValueError, "sum to 1"):
            assign_timestamp_blocks(
                frame,
                timestamp_column="timestamp",
                train_ratio=0.6,
                validation_ratio=0.2,
                test_ratio=0.3,
            )

    def test_rows_sharing_a_source_timestamp_cannot_cross_partition(self) -> None:
        frame = pd.DataFrame({
            "sample_id": [f"s{i}" for i in range(12)],
            "timestamp": pd.date_range("2024-01-01", periods=12, freq="h", tz="UTC"),
            "environment_timestamp": [
                "2024-01-01T00:00Z", "2024-01-01T01:00Z", "2024-01-01T02:00Z", "2024-01-01T03:00Z",
                "2024-01-01T04:00Z", "2024-01-01T05:00Z", "2024-01-01T06:00Z", "2024-01-01T07:00Z",
                "2024-01-01T08:00Z", "2024-01-01T09:00Z", "2024-01-01T10:00Z", "2024-01-01T11:00Z",
            ],
        })
        frame.loc[10, "environment_timestamp"] = frame.loc[1, "environment_timestamp"]
        splits, _ = assign_timestamp_blocks(
            frame,
            timestamp_column="timestamp",
            train_ratio=0.70,
            validation_ratio=0.15,
            test_ratio=0.15,
            shared_timestamp_columns=("environment_timestamp",),
        )
        self.assertEqual(splits.loc[1, "partition"], splits.loc[10, "partition"])
        self.assertEqual(splits.loc[1, "timestamp_block_id"], splits.loc[10, "timestamp_block_id"])


if __name__ == "__main__":
    unittest.main()
