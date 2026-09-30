from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.external_features.contracts import ExternalFeatureConfig
from Backend.Benchmark.external_features.pipeline import run_external_feature_processing
from Backend.Benchmark.external_features.profiles import ExternalFeatureProfile
from Backend.Benchmark.external_features.windowing import build_external_feature_matrix
from Backend.Benchmark.pretrain_audit import PretrainAuditConfig, run_pretrain_audit


class ExternalFeatureTests(unittest.TestCase):
    def test_pipeline_persists_a_source_bound_feature_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            intake_dir = Path(temp_dir) / "intake"
            intake_dir.mkdir()
            canonical_path = intake_dir / "canonical.parquet"
            pd.DataFrame(
                {
                    "sample_id": ["u1", "u2", "u3"],
                    "timestamp": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 01:00", "2024-01-01 02:00"]),
                    "sensor.co": [10.0, 20.0, 30.0],
                    "sensor.nmhc": [1.0, 2.0, 3.0],
                    "sensor.nox": [4.0, 5.0, 6.0],
                    "sensor.no2": [7.0, 8.0, 9.0],
                    "sensor.o3": [10.0, 11.0, 12.0],
                    "context.temperature_c": [20.0, 21.0, 22.0],
                    "context.relative_humidity_pct": [40.0, 41.0, 42.0],
                    "context.absolute_humidity": [0.4, 0.5, 0.6],
                    "criterion.co_gt_mg_m3": [1.0, 2.0, 3.0],
                }
            ).to_parquet(canonical_path, index=False)
            (intake_dir / "artifact_catalog.json").write_text(
                json.dumps([
                    {"path": "canonical.parquet", "sha256": hashlib.sha256(canonical_path.read_bytes()).hexdigest()},
                    {"path": "run_manifest.json", "sha256": "manifest-hash-placeholder"},
                ]),
                encoding="utf-8",
            )
            raw_manifest_path = intake_dir / "raw_manifest.json"
            raw_manifest_path.write_text(json.dumps({"dataset_id": "uci_air_quality_360"}), encoding="utf-8")
            intake_manifest_path = intake_dir / "run_manifest.json"
            intake_payload = {
                        "dataset_id": "uci_air_quality_360",
                        "run_id": "intake-fixture",
                        "raw_manifest_path": str(raw_manifest_path.resolve()),
                        "raw_manifest_sha256": hashlib.sha256(raw_manifest_path.read_bytes()).hexdigest(),
                        "adapter_audit": {
                            "column_roles": {
                                "sensor.co": "measurement",
                                "criterion.co_gt_mg_m3": "criterion_only",
                            }
                        },
                    }
            intake_manifest_path.write_text(json.dumps(intake_payload), encoding="utf-8")
            catalog = json.loads((intake_dir / "artifact_catalog.json").read_text(encoding="utf-8"))
            catalog[-1]["sha256"] = hashlib.sha256(intake_manifest_path.read_bytes()).hexdigest()
            (intake_dir / "artifact_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            result = run_external_feature_processing(
                ExternalFeatureConfig(
                    canonical_path=canonical_path,
                    intake_manifest_path=intake_manifest_path,
                    output_root=Path(temp_dir) / "features",
                    window_hours=(3,),
                )
            )
            registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
            features = pd.read_parquet(result.feature_matrix_path)

            self.assertEqual(result.row_count, 3)
            self.assertEqual(
                registry["feature_groups"]["values"]["columns"],
                [
                    "sensor.co", "sensor.nmhc", "sensor.nox", "sensor.no2", "sensor.o3",
                    "context.temperature_c", "context.relative_humidity_pct", "context.absolute_humidity",
                ],
            )
            self.assertIn("window_3h", registry["feature_groups"])
            self.assertNotIn("criterion.co_gt_mg_m3", features.columns)
            self.assertTrue((result.output_dir / "artifact_catalog.json").is_file())
            labels_path = Path(temp_dir) / "labels.parquet"
            splits_path = Path(temp_dir) / "splits.parquet"
            pd.DataFrame({"sample_id": ["u1", "u2", "u3"], "target.hum": [0, 1, 0]}).to_parquet(labels_path, index=False)
            pd.DataFrame(
                {"sample_id": ["u1", "u2", "u3"], "partition": ["train", "train", "test"]}
            ).to_parquet(splits_path, index=False)
            audit = run_pretrain_audit(
                PretrainAuditConfig(
                    feature_matrix_path=result.feature_matrix_path,
                    feature_registry_path=result.registry_path,
                    labels_path=labels_path,
                    splits_path=splits_path,
                    selected_groups=("values",),
                    target_columns=("target.hum",),
                    output_root=Path(temp_dir) / "audit",
                )
            )
            self.assertEqual(audit.status, "ready_for_model_policy_review")

            intake_payload["adapter_audit"]["column_roles"]["criterion.co_gt_mg_m3"] = "measurement"
            intake_manifest_path.write_text(json.dumps(intake_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Intake manifest checksum"):
                run_external_feature_processing(
                    ExternalFeatureConfig(
                        canonical_path=canonical_path,
                        intake_manifest_path=intake_manifest_path,
                        output_root=Path(temp_dir) / "tampered_features",
                        window_hours=(3,),
                    )
                )

            intake_payload["adapter_audit"]["column_roles"]["criterion.co_gt_mg_m3"] = "measurement"
            intake_manifest_path.write_text(json.dumps(intake_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Intake manifest checksum"):
                run_external_feature_processing(
                    ExternalFeatureConfig(
                        canonical_path=canonical_path,
                        intake_manifest_path=intake_manifest_path,
                        output_root=Path(temp_dir) / "tampered_features",
                        window_hours=(3,),
                    )
                )

    def test_windows_are_causal_and_reset_between_entities(self) -> None:
        canonical = pd.DataFrame(
            {
                "sample_id": ["a1", "b1", "a2", "b2"],
                "timestamp": pd.to_datetime(
                    ["2024-01-01T00:00Z", "2024-01-01T00:00Z", "2024-01-01T02:00Z", "2024-01-01T02:00Z"]
                ),
                "entity_id": ["line_1", "line_2", "line_1", "line_2"],
                "soil_moisture_pct": [10.0, 100.0, 20.0, 200.0],
                "water_volume_m3": [1.0, 2.0, 3.0, 4.0],
            }
        )
        profile = ExternalFeatureProfile(
            dataset_id="stuard_tomato_irrigation_2023",
            timestamp_column="timestamp",
            group_columns=("entity_id",),
            value_columns=("soil_moisture_pct",),
        )
        features, groups, _ = build_external_feature_matrix(
            canonical=canonical,
            profile=profile,
            window_hours=(3,),
            min_window_observations=2,
        )

        self.assertEqual(features["sample_id"].tolist(), ["a1", "a2", "b1", "b2"])
        self.assertEqual(features.loc[1, "soil_moisture_pct__3h_mean"], 15.0)
        self.assertEqual(features.loc[3, "soil_moisture_pct__3h_mean"], 150.0)
        self.assertNotIn("water_volume_m3", features.columns)
        self.assertIn("window_3h", groups)

    def test_time_window_excludes_values_older_than_horizon_and_forbidden_criteria(self) -> None:
        canonical = pd.DataFrame(
            {
                "sample_id": ["u1", "u2", "u3"],
                "timestamp": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 02:00", "2024-01-01 04:00"]),
                "sensor.co": [10.0, 20.0, 40.0],
                "criterion.co_gt_mg_m3": [1.0, 2.0, 4.0],
            }
        )
        profile = ExternalFeatureProfile(
            dataset_id="uci_air_quality_360",
            timestamp_column="timestamp",
            group_columns=(),
            value_columns=("sensor.co",),
        )
        features, _, _ = build_external_feature_matrix(
            canonical=canonical,
            profile=profile,
            window_hours=(3,),
            min_window_observations=2,
        )

        self.assertTrue(pd.isna(features.loc[0, "sensor.co__3h_mean"]))
        self.assertEqual(features.loc[1, "sensor.co__3h_mean"], 15.0)
        self.assertEqual(features.loc[2, "sensor.co__3h_mean"], 30.0)
        self.assertFalse(any("criterion" in column for column in features.columns))


if __name__ == "__main__":
    unittest.main()
