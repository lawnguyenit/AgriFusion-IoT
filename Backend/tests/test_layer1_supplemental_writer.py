from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Core.layer1.writers.supplemental import SupplementalOutputWriter


class Layer1SupplementalWriterTests(unittest.TestCase):
    def test_writer_creates_segment_manifest_and_buffer_reason_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "Layer1"
            writer = SupplementalOutputWriter(output_root)
            writer.ensure_directories()

            canonical_df = pd.DataFrame(
                [
                    {
                        "record.id": "r1",
                        "record.node_id": "Node1",
                        "record.event_key": "1",
                        "record.ts_sample": 1000,
                        "record.ts_server": 1080,
                        "record.segment_id": "node1_seg_0001",
                        "record.segment_index": 1,
                        "record.segment_boundary_before": True,
                        "record.segment_expected_interval_sec": 1000,
                        "delivery.buffer_reason": None,
                    },
                    {
                        "record.id": "r2",
                        "record.node_id": "Node1",
                        "record.event_key": "2",
                        "record.ts_sample": 2000,
                        "record.ts_server": 2080,
                        "record.segment_id": "node1_seg_0002",
                        "record.segment_index": 2,
                        "record.segment_boundary_before": True,
                        "record.segment_expected_interval_sec": 1000,
                        "delivery.buffer_reason": "http_action_fail",
                    },
                ]
            )
            audit_df = pd.DataFrame(
                [
                    {
                        "record.id": "r2",
                        "record.segment_id": "node1_seg_0002",
                        "record.node_id": "Node1",
                        "delivery.buffer_reason": "http_action_fail",
                        "buffer_reason_raw": "/Node1/path -> http_action_fail | ok",
                    }
                ]
            )
            segment_summaries = [
                {
                    "node_id": "Node1",
                    "segment_id": "node1_seg_0001",
                    "segment_index": 1,
                    "row_count": 1,
                    "start_ts_sample": 1000,
                    "end_ts_sample": 1000,
                    "start_record_id": "r1",
                    "end_record_id": "r1",
                    "expected_interval_sec": 1000,
                },
                {
                    "node_id": "Node1",
                    "segment_id": "node1_seg_0002",
                    "segment_index": 2,
                    "row_count": 1,
                    "start_ts_sample": 2000,
                    "end_ts_sample": 2000,
                    "start_record_id": "r2",
                    "end_record_id": "r2",
                    "expected_interval_sec": 1000,
                },
            ]

            audit_path = writer.write_buffer_reason_audit(audit_df)
            manifest_path = writer.write_segment_outputs(
                canonical_df=canonical_df,
                segment_summaries=segment_summaries,
                export_debug_views=True,
            )

            self.assertTrue(audit_path.exists())
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["segment_count"], 2)
            self.assertTrue(
                (output_root / "segments" / "node1_seg_0001" / "canonical").exists()
            )


if __name__ == "__main__":
    unittest.main()
