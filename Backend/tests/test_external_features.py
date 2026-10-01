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
from Backend.Benchmark.pretrain_audit.selection import resolve_feature_selection


class ExternalFeatureTests(unittest.TestCase):
    def test_pipeline_persists_a_source_bound_feature_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            intake_dir = Path(temp_dir) / "intake"
            intake_dir.mkdir()
            canonical_path = intake_dir / "canonical.parquet"
            pd.DataFrame(
                {
                    "sample_id": ["u1", "u2", "u3", "u4"],
                    "timestamp": pd.to_datetime(["2005-02-28 21:00", "2005-02-28 22:00", "2005-02-28 23:00", "2005-03-01 00:00"]),
                    "sensor.co": [10.0, 20.0, 30.0, 40.0],
                    "sensor.nmhc": [1.0, 2.0, 3.0, 4.0],
                    "sensor.nox": [4.0, 5.0, 6.0, 7.0],
                    "sensor.no2": [7.0, 8.0, 9.0, 10.0],
                    "sensor.o3": [10.0, 11.0, 12.0, 13.0],
                    "context.temperature_c": [20.0, 21.0, 22.0, 23.0],
                    "context.relative_humidity_pct": [40.0, 41.0, 42.0, 43.0],
                    "context.absolute_humidity": [0.4, 0.5, 0.6, 0.7],
                    "criterion.co_gt_mg_m3": [1.0, 2.0, 3.0, 4.0],
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
                            "data_semantics": {
                                "target_defining_reference_measurements": ["criterion.co_gt_mg_m3"],
                                "independent_criterion": False,
                            },
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
            self.assertEqual(features["sample_id"].tolist(), ["u1", "u2", "u3"])
            self.assertEqual(registry["source_scope"]["excluded_row_count"], 1)
            self.assertEqual(
                registry["feature_groups"]["values"]["columns"],
                [
                    "sensor.co", "sensor.nmhc", "sensor.nox", "sensor.no2", "sensor.o3",
                    "context.temperature_c", "context.relative_humidity_pct", "context.absolute_humidity",
                ],
            )
            self.assertIn("window_3h", registry["feature_groups"])
            self.assertNotIn("irrigation_context", registry["feature_group_roles"])
            self.assertFalse(registry["data_semantics"]["independent_criterion"])
            self.assertEqual(
                registry["feature_group_roles"],
                {"values": "strict_sensor_measurements", "window_3h": "causal_window_derived_measurements"},
            )
            feature_report = (result.output_dir / "report.md").read_text(encoding="utf-8")
            self.assertIn("Target-defining reference measurements", feature_report)
            self.assertNotIn("irrigation", registry["feature_selection_policy"].lower())
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

            unknown_labels_path = Path(temp_dir) / "labels_with_unknown.parquet"
            pd.DataFrame({
                "sample_id": ["u1", "u2", "u3"],
                "target.hum": pd.Series([0, 1, pd.NA], dtype="Int64"),
                "target.co": pd.Series([1, 0, pd.NA], dtype="Int64"),
                "status.target.hum": ["KNOWN", "KNOWN", "PERSISTENCE_HISTORY_INSUFFICIENT"],
                "status.target.co": ["KNOWN", "KNOWN", "PERSISTENCE_HISTORY_INSUFFICIENT"],
            }).to_parquet(unknown_labels_path, index=False)
            unknown_training_splits_path = Path(temp_dir) / "splits_with_unknown_training.parquet"
            pd.DataFrame(
                {"sample_id": ["u1", "u2", "u3"], "partition": ["train", "train", "train"]}
            ).to_parquet(unknown_training_splits_path, index=False)
            eligible_audit = run_pretrain_audit(
                PretrainAuditConfig(
                    feature_matrix_path=result.feature_matrix_path,
                    feature_registry_path=result.registry_path,
                    labels_path=unknown_labels_path,
                    splits_path=unknown_training_splits_path,
                    selected_groups=("values",),
                    target_columns=("target.hum", "target.co"),
                    output_root=Path(temp_dir) / "eligible_audit",
                    exclude_unknown_targets=True,
                )
            )
            self.assertEqual(eligible_audit.status, "ready_for_model_policy_review")
            self.assertEqual(eligible_audit.row_count, 2)
            eligible_manifest = json.loads((eligible_audit.output_dir / "audit_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(eligible_manifest["alignment"]["excluded_unknown_training_row_count"], 1)
            eligible_labels = pd.read_parquet(eligible_audit.output_dir / "selected_labels.parquet")
            self.assertTrue(eligible_labels[["target.hum", "target.co"]].notna().all().all())
            eligibility = pd.read_csv(eligible_audit.output_dir / "eligibility_audit.csv")
            excluded = eligibility.loc[eligibility["sample_id"].eq("u3")].iloc[0]
            self.assertFalse(bool(excluded["included_in_handoff"]))
            self.assertEqual(
                excluded["eligibility_reason"],
                "PERSISTENCE_HISTORY_INSUFFICIENT|PERSISTENCE_HISTORY_INSUFFICIENT",
            )

            evaluation_audit = run_pretrain_audit(
                PretrainAuditConfig(
                    feature_matrix_path=result.feature_matrix_path,
                    feature_registry_path=result.registry_path,
                    labels_path=unknown_labels_path,
                    splits_path=splits_path,
                    selected_groups=("values",),
                    target_columns=("target.hum", "target.co"),
                    output_root=Path(temp_dir) / "evaluation_audit",
                    exclude_unknown_targets=True,
                )
            )
            self.assertEqual(evaluation_audit.row_count, 3)
            evaluation_manifest = json.loads((evaluation_audit.output_dir / "audit_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(evaluation_manifest["alignment"]["retained_unknown_evaluation_row_count"], 1)
            evaluation_labels = pd.read_parquet(evaluation_audit.output_dir / "selected_labels.parquet")
            self.assertTrue(pd.isna(evaluation_labels.loc[evaluation_labels["sample_id"].eq("u3"), "target.hum"]).all())

            support_gate_path = Path(temp_dir) / "support_gate.csv"
            pd.DataFrame({
                "label_column": ["target.hum"] * 3,
                "partition": ["train", "validation", "test"],
                "support_gate_pass": [True, False, True],
            }).to_csv(support_gate_path, index=False)
            gated_audit = run_pretrain_audit(
                PretrainAuditConfig(
                    feature_matrix_path=result.feature_matrix_path,
                    feature_registry_path=result.registry_path,
                    labels_path=labels_path,
                    splits_path=splits_path,
                    selected_groups=("values",),
                    target_columns=("target.hum",),
                    output_root=Path(temp_dir) / "gated_audit",
                    support_gate_path=support_gate_path,
                )
            )
            self.assertEqual(gated_audit.status, "blocked")
            gated_manifest = json.loads((gated_audit.output_dir / "audit_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("one_or_more_targets_fail_external_support_gate", gated_manifest["blocked_reasons"])

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

    def test_current_measurements_are_numeric_with_parse_and_nonfinite_diagnostics(self) -> None:
        canonical = pd.DataFrame({
            "sample_id": ["s1", "s2", "s3"],
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="h"),
            "sensor.co": ["12.5", "not-a-number", "inf"],
        })
        profile = ExternalFeatureProfile(
            dataset_id="uci_air_quality_360",
            timestamp_column="timestamp",
            group_columns=(),
            value_columns=("sensor.co",),
        )
        features, _, quality = build_external_feature_matrix(
            canonical=canonical,
            profile=profile,
            window_hours=(3,),
            min_window_observations=1,
        )
        self.assertEqual(float(features.loc[0, "sensor.co"]), 12.5)
        self.assertTrue(pd.isna(features.loc[1, "sensor.co"]))
        self.assertTrue(pd.isna(features.loc[2, "sensor.co"]))
        row = quality.loc[quality["feature"].eq("sensor.co")].iloc[0]
        self.assertEqual(row["source_dtype"], "object")
        self.assertEqual(row["parse_failure_count"], 1)
        self.assertEqual(row["nonfinite_count"], 1)
        self.assertEqual(row["missing_count"], 2)

    def test_stuard_context_is_separate_and_target_moisture_is_absent(self) -> None:
        from Backend.Benchmark.external_features.profiles import resolve_profile

        profile = resolve_profile("stuard_tomato_irrigation_2023", {})
        canonical = pd.DataFrame(
            {
                "sample_id": ["a", "b", "c"],
                "timestamp": pd.date_range("2024-01-01", periods=3, freq="10min", tz="UTC"),
                "entity_id": ["line_1"] * 3,
                "soil_moisture_pct": [10.0, 9.0, 8.0],
                "soil_temperature_c": [20.0, 21.0, 22.0],
                "soil_ec_us_cm": [100.0, 101.0, 102.0],
                "air_temperature_c": [24.0, 24.0, 24.0],
                "air_humidity_pct": [40.0, 41.0, 42.0],
                "air_co2_ppm": [400.0, 401.0, 402.0],
                "air_pressure_hpa": [1000.0, 1001.0, 1002.0],
                "water_timestamp": pd.date_range("2024-01-01", periods=3, freq="10min", tz="UTC"),
                "water_volume_m3": [1.0, 1.1, 1.4],
                "water_alignment_age_sec": [0.0, 0.0, 0.0],
            }
        )
        features, groups, _ = build_external_feature_matrix(
            canonical=canonical,
            profile=profile,
            window_hours=(1,),
            min_window_observations=2,
        )
        self.assertNotIn("soil_moisture_pct", features.columns)
        self.assertFalse(any(column.startswith("soil_moisture_pct__") for column in features.columns))
        self.assertEqual(groups["irrigation_context"], ["water_volume_increment_m3", "water_alignment_age_sec"])
        self.assertAlmostEqual(float(features.loc[2, "water_volume_increment_m3"]), 0.3)

    def test_pretrain_selector_rejects_target_source_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            registry_path = Path(temporary) / "registry.json"
            columns = ["soil_moisture_pct__3h_mean"]
            from Backend.Benchmark.dataset_views.validators import stable_hash_object

            registry_path.write_text(json.dumps({
                "feature_groups": {
                    "bad_window": {
                        "columns": columns,
                        "columns_hash": stable_hash_object(columns),
                    }
                },
                "ordered_feature_columns": columns,
                "excluded_target_source_columns": ["soil_moisture_pct"],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Target source fields"):
                resolve_feature_selection(
                    registry_path=registry_path,
                    selected_groups=("bad_window",),
                    available_columns=["sample_id", *columns],
                )


if __name__ == "__main__":
    unittest.main()
