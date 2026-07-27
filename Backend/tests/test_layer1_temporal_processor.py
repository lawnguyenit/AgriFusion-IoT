from __future__ import annotations

import unittest

import pandas as pd

from Backend.Core.layer1.contracts import TemporalSettings
from Backend.Core.layer1.processors.temporal import apply_temporal_features


class Layer1TemporalProcessorTests(unittest.TestCase):
    def test_temporal_processor_splits_segments_and_resets_gap_features(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "record.id": "r1",
                    "record.node_id": "Node1",
                    "record.event_key": "1",
                    "record.ts_sample": 1000,
                    "record.ts_server": 1080,
                    "delivery.is_buffered_replay": False,
                },
                {
                    "record.id": "r2",
                    "record.node_id": "Node1",
                    "record.event_key": "2",
                    "record.ts_sample": 2000,
                    "record.ts_server": 2080,
                    "delivery.is_buffered_replay": False,
                },
                {
                    "record.id": "r3",
                    "record.node_id": "Node1",
                    "record.event_key": "3",
                    "record.ts_sample": 3000,
                    "record.ts_server": 3080,
                    "delivery.is_buffered_replay": False,
                },
                {
                    "record.id": "r4",
                    "record.node_id": "Node1",
                    "record.event_key": "4",
                    "record.ts_sample": 6000,
                    "record.ts_server": 6080,
                    "delivery.is_buffered_replay": False,
                },
                {
                    "record.id": "r5",
                    "record.node_id": "Node1",
                    "record.event_key": "5",
                    "record.ts_sample": 100000,
                    "record.ts_server": 100080,
                    "delivery.is_buffered_replay": False,
                },
                {
                    "record.id": "r6",
                    "record.node_id": "Node1",
                    "record.event_key": "6",
                    "record.ts_sample": 101000,
                    "record.ts_server": 101080,
                    "delivery.is_buffered_replay": False,
                },
            ]
        )

        processed, duplicate_count, segment_summaries = apply_temporal_features(
            dataframe,
            TemporalSettings(
                expected_interval_sec=900,
                gap_threshold_sec=1500,
                segment_break_threshold_sec=20000,
            ),
        )

        self.assertEqual(duplicate_count, 0)
        self.assertEqual(len(segment_summaries), 2)
        self.assertEqual(
            processed["record.segment_id"].tolist(),
            [
                "node1_seg_0001",
                "node1_seg_0001",
                "node1_seg_0001",
                "node1_seg_0001",
                "node1_seg_0002",
                "node1_seg_0002",
            ],
        )
        self.assertEqual(processed.loc[0, "record.segment_boundary_before"], True)
        self.assertEqual(processed.loc[4, "record.segment_boundary_before"], True)
        self.assertTrue(pd.isna(processed.loc[4, "record.delta_prev_sec"]))
        self.assertEqual(processed.loc[4, "record.missing_slot_count"], 0)
        self.assertEqual(processed.loc[0, "record.segment_expected_interval_sec"], 1000)
        self.assertEqual(processed.loc[5, "record.segment_expected_interval_sec"], 1000)
        self.assertEqual(processed.loc[3, "record.delta_prev_sec"], 3000)
        self.assertEqual(processed.loc[3, "record.missing_slot_count"], 2)
        self.assertEqual(processed.loc[3, "record.gap_flag"], True)


if __name__ == "__main__":
    unittest.main()
