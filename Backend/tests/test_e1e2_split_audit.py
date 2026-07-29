from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.evaluation_protocols.e1e2_split_audit import build_e1e2_split_audit


class E1E2SplitAuditTests(unittest.TestCase):
    def test_build_e1e2_split_audit_reports_partition_support(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protocol_run_dir = root / "evaluation_protocols_run"
            weak_labels_run_dir = root / "weak_labels_run"
            (protocol_run_dir / "domain_manifests").mkdir(parents=True, exist_ok=True)
            (weak_labels_run_dir / "point").mkdir(parents=True, exist_ok=True)
            (weak_labels_run_dir / "v2").mkdir(parents=True, exist_ok=True)

            sample_rows: list[dict[str, object]] = []
            point_rows: list[dict[str, object]] = []
            v2_rows: list[dict[str, object]] = []
            base_time = pd.Timestamp("2026-04-01T00:00:00+07:00")
            shared_cycle = [
                "normal_point",
                "low_relative_moisture_point",
                "unknown_environment_point",
            ]
            sparse_tail_cycle = [
                "normal_point",
                "low_relative_moisture_point",
                "normal_point",
            ]

            for index in range(20):
                sample_id = f"sample_{index:02d}"
                sample_rows.append(
                    {
                        "sample_id": sample_id,
                        "timestamp_local": (base_time + pd.Timedelta(minutes=10 * index)).isoformat(),
                        "environment_id": "E1" if index < 14 else "E2",
                        "deployment_id": "dep_1",
                        "segment_id": "seg_1",
                        "analysis_status": "PRIMARY_LOCKED",
                        "boundary_status": "PROTOCOL_LOCKED",
                    }
                )
                point_rows.append(
                    {
                        "sample_id": sample_id,
                        "label_task_id": "v0_point_train",
                        "label_status": "LABELED",
                        "label_name": shared_cycle[index % len(shared_cycle)],
                    }
                )
                v2_rows.append(
                    {
                        "sample_id": sample_id,
                        "label_task_id": "v2_same_y_3h",
                        "label_status": "LABELED",
                        "label_name": shared_cycle[index % len(shared_cycle)],
                    }
                )
                v2_rows.append(
                    {
                        "sample_id": sample_id,
                        "label_task_id": "v2_same_y_8h",
                        "label_status": "LABELED",
                        "label_name": sparse_tail_cycle[index - 17] if index >= 17 else shared_cycle[index % len(shared_cycle)],
                    }
                )

            pd.DataFrame(sample_rows).convert_dtypes().to_parquet(
                protocol_run_dir / "domain_manifests" / "sample_environment_manifest.parquet",
                index=False,
            )
            pd.DataFrame(point_rows).convert_dtypes().to_parquet(
                weak_labels_run_dir / "point" / "point_labels_train.parquet",
                index=False,
            )
            pd.DataFrame(v2_rows).convert_dtypes().to_parquet(
                weak_labels_run_dir / "v2" / "v2_same_y_labels.parquet",
                index=False,
            )

            result = build_e1e2_split_audit(
                protocol_run_dir=protocol_run_dir,
                weak_labels_run_dir=weak_labels_run_dir,
            )

            summary = result["summary"].set_index("audit_task_id")
            self.assertTrue(bool(summary.loc["v0_v1_point_train", "all_partitions_have_full_class_support"]))
            self.assertTrue(bool(summary.loc["v2_same_y_3h", "all_partitions_have_full_class_support"]))
            self.assertFalse(bool(summary.loc["v2_same_y_8h", "all_partitions_have_full_class_support"]))
            self.assertEqual(summary.loc["v2_same_y_8h", "test_missing_classes_json"], "[\"unknown_environment_point\"]")
            self.assertTrue((result["output_dir"] / "ARTIFACT_GUIDE.md").exists())
            self.assertTrue((result["output_dir"] / "task_split_summary.csv").exists())


if __name__ == "__main__":
    unittest.main()
