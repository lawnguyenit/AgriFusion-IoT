from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import resolve_view_ids
from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.tests.dataset_views_helpers import create_dataset_views_v3_fixture


class DatasetViewsV3OperationalLineageTests(unittest.TestCase):
    def test_v3_family_alias_expands_to_all_subviews(self) -> None:
        self.assertEqual(
            resolve_view_ids(("v3",)),
            ("v3_direct", "v3_derived", "v3_independent", "v3_pre_onset"),
        )

    def test_v3_materialization_writes_shared_family_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            self.assertFalse((result.output_dir / "V3").exists())
            self.assertTrue((result.output_dir / "shared" / "v3_evidence_ledger.csv").exists())
            self.assertTrue((result.output_dir / "shared" / "v3_event_registry.csv").exists())
            self.assertTrue((result.output_dir / "reports" / "v3_generation_report.md").exists())
            self.assertFalse((result.output_dir / "views" / "v5_proxy_reduced_draft").exists())

    def test_v3_direct_contains_only_direct_genealogy_features(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3_direct",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            catalog_df = pd.read_csv(result.output_dir / "views" / "v3_direct" / "feature_catalog.csv")
            self.assertTrue((catalog_df["genealogy"] == "direct_rule").all())
            self.assertNotIn("big_label", pd.read_csv(result.output_dir / "views" / "v3_direct" / "X.csv").columns)

    def test_v3_independent_excludes_direct_and_derived_features(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3_independent",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            catalog_df = pd.read_csv(result.output_dir / "views" / "v3_independent" / "feature_catalog.csv")
            self.assertTrue((catalog_df["genealogy"] == "independent_process").all())
            feature_df = pd.read_parquet(result.output_dir / "views" / "v3_independent" / "X.parquet")
            self.assertNotIn("sht.read_ok", feature_df.columns)
            self.assertNotIn("npk.valid", feature_df.columns)
            self.assertNotIn("record.upload_delay_sec", feature_df.columns)
            self.assertNotIn("device.cycle_duration_ms", feature_df.columns)
            self.assertNotIn("sht.read_elapsed_ms", feature_df.columns)
            self.assertEqual(
                sorted(
                    {
                        column.split("__", 1)[0]
                        for column in feature_df.columns
                    }
                ),
                ["device.heap_free", "network.signal_dbm"],
            )

    def test_v3_derived_prunes_duplicate_and_alias_features_from_published_x(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3_derived",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            manifest = json.loads(
                (result.output_dir / "views" / "v3_derived" / "manifest.json").read_text(encoding="utf-8")
            )
            feature_df = pd.read_parquet(result.output_dir / "views" / "v3_derived" / "X.parquet")
            ledger_df = pd.read_csv(result.output_dir / "shared" / "v3_evidence_ledger.csv")

            self.assertGreater(manifest["feature_reduction"]["dropped_feature_count"], 0)
            self.assertIn("npk.crc_ok__3c_true_count", feature_df.columns)
            self.assertNotIn("npk.frame_ok__3c_true_count", feature_df.columns)
            self.assertTrue((ledger_df["feature_name"] == "npk.frame_ok__3c_true_count").any())

    def test_v3_pre_onset_preserves_row_alignment_and_emits_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3_pre_onset",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            metadata_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "metadata.parquet")
            x_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "X.parquet")
            y_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "y.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "target_audit.parquet")

            self.assertEqual(len(metadata_df), len(x_df))
            self.assertEqual(len(metadata_df), len(y_df))
            self.assertEqual(len(metadata_df), len(audit_df))
            self.assertEqual(metadata_df["record.id"].tolist(), y_df["record.id"].tolist())

            row_r303 = int(metadata_df.index[metadata_df["record.id"] == "r303"][0])
            self.assertEqual(metadata_df.loc[row_r303, "event_phase"], "pre_event")
            self.assertEqual(int(y_df.loc[row_r303, "fault_onset_system_context_within_1c"]), 1)
            self.assertIn("has_system_evidence", metadata_df.columns)
            self.assertIn("priority_reason", audit_df.columns)

    def test_v3_pre_onset_marks_missing_future_context_as_ineligible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3_pre_onset",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            metadata_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "metadata.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "target_audit.parquet")
            y_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "y.parquet")
            row_r306 = int(metadata_df.index[metadata_df["record.id"] == "r306"][0])
            self.assertTrue(pd.isna(y_df.loc[row_r306, "fault_onset_system_context_within_3c"]))
            self.assertEqual(
                audit_df.loc[row_r306, "fault_onset_system_context_within_3c__reason"],
                "missing_future_event_context",
            )

    def test_v3_event_and_target_audit_preserve_overlap_and_priority_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3_pre_onset",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            metadata_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "metadata.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v3_pre_onset" / "target_audit.parquet")
            event_registry_df = pd.read_parquet(result.output_dir / "shared" / "v3_event_registry.parquet")

            row_r306 = int(metadata_df.index[metadata_df["record.id"] == "r306"][0])
            self.assertTrue(bool(metadata_df.loc[row_r306, "has_system_evidence"]))
            self.assertTrue(bool(metadata_df.loc[row_r306, "has_sensor_evidence"]))
            self.assertEqual(metadata_df.loc[row_r306, "primary_label"], "sensor_fault_context")
            self.assertEqual(
                metadata_df.loc[row_r306, "priority_reason"],
                "sensor_priority_over_system_overlap",
            )
            self.assertEqual(
                audit_df.loc[row_r306, "priority_reason"],
                "sensor_priority_over_system_overlap",
            )
            self.assertIn("has_system_evidence", event_registry_df.columns)
            self.assertIn("primary_label_rule", event_registry_df.columns)

    def test_v3_manifest_records_causal_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v3_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v3_independent",),
                    legacy_event_csv_path=fixture["legacy_event_csv_path"],
                )
            )

            manifest = json.loads(
                (result.output_dir / "views" / "v3_independent" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(manifest["causal"])
            self.assertTrue(manifest["segment_aware"])
            self.assertTrue(manifest["continuity_reset"])
            self.assertFalse(manifest["synthetic_rows"])
            self.assertEqual(manifest["imputation"], "none")


if __name__ == "__main__":
    unittest.main()
