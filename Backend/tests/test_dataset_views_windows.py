from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import resolve_view_ids
from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.tests.dataset_views_helpers import create_dataset_views_v2_fixture


class DatasetViewsWindowTests(unittest.TestCase):
    def test_v2_family_alias_expands_to_split_subviews(self) -> None:
        self.assertEqual(
            resolve_view_ids(("v2",)),
            (
                "v2_minimal_sensor_window_3h",
                "v2_sensor_row_window_3h",
            ),
        )

    def test_v2_alias_materializes_only_primary_3h_subviews(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2",),
                )
            )

            v2m3 = pd.read_parquet(result.output_dir / "views" / "v2_minimal_sensor_window_3h" / "X.parquet")
            v2r3 = pd.read_parquet(result.output_dir / "views" / "v2_sensor_row_window_3h" / "X.parquet")
            self.assertFalse((result.output_dir / "views" / "v2_minimal_sensor_window_8h").exists())
            self.assertFalse((result.output_dir / "views" / "v2_sensor_row_window_8h").exists())

            self.assertEqual(v2m3.shape[1], 30)
            self.assertEqual(v2r3.shape[1], 54)

            self.assertIn("sht.temp_c__3h_median", v2m3.columns)
            self.assertNotIn("sht.temp_c__8h_median", v2m3.columns)
            self.assertNotIn("npk.ph", v2m3.columns)
            self.assertIn("npk.ph", v2r3.columns)

    def test_explicit_8h_subviews_remain_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_minimal_sensor_window_8h", "v2_sensor_row_window_8h"),
                )
            )

            self.assertTrue((result.output_dir / "views" / "v2_minimal_sensor_window_8h" / "X.parquet").exists())
            self.assertTrue((result.output_dir / "views" / "v2_sensor_row_window_8h" / "X.parquet").exists())

    def test_v2_preserves_row_identity_and_no_synthetic_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            canonical_df = pd.read_csv(fixture["canonical_path"])
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "window_quality_audit.parquet")

            self.assertEqual(len(canonical_df), len(row_index_df))
            self.assertEqual(len(canonical_df), len(feature_df))
            self.assertEqual(len(canonical_df), len(audit_df))
            self.assertEqual(canonical_df["record.id"].tolist(), row_index_df["record.id"].tolist())
            self.assertFalse(any(column.endswith("_coverage_ratio") for column in feature_df.columns))
            self.assertFalse(any(column.endswith("_valid_observation_count") for column in feature_df.columns))
            self.assertNotIn("3h_expected_observation_count", feature_df.columns)

    def test_v2_legacy_combined_view_remains_supported_for_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            self.assertIn("sht.temp_c__3h_median", feature_df.columns)
            self.assertIn("sht.temp_c__8h_median", feature_df.columns)

    def test_v2_missing_values_never_become_zero_and_invalid_current_delta_is_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            row_position = int(row_index_df.index[row_index_df["record.id"] == "r8"][0])
            self.assertTrue(pd.isna(feature_df.loc[row_position, "npk.ec"]))
            self.assertTrue(pd.isna(feature_df.loc[row_position, "npk.ec__3h_delta"]))
            self.assertNotEqual(feature_df.loc[row_position, "npk.ec"], 0.0)

    def test_v2_replayed_records_are_ordered_by_sample_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "window_quality_audit.parquet")
            row_position = int(row_index_df.index[row_index_df["record.id"] == "r7"][0])
            self.assertEqual(int(audit_df.loc[row_position, "3h_valid_observation_count"]), 8)
            self.assertAlmostEqual(float(audit_df.loc[row_position, "3h_span_coverage_ratio"]), 0.5833333333333334)

    def test_v2_invalid_observation_does_not_create_fake_extreme_range(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            row_position = int(row_index_df.index[row_index_df["record.id"] == "r10"][0])
            self.assertAlmostEqual(feature_df.loc[row_position, "npk.ec__3h_range"], 1.0)

    def test_v2_insufficient_evidence_produces_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            self.assertTrue(pd.isna(feature_df.loc[0, "sht.temp_c__3h_median"]))
            self.assertTrue(pd.isna(feature_df.loc[0, "sht.temp_c__8h_median"]))
            self.assertTrue(pd.isna(feature_df.loc[0, "sht.temp_c__3h_slope_per_hour"]))
            self.assertTrue(pd.isna(feature_df.loc[0, "sht.temp_c__8h_slope_per_hour"]))

    def test_v2_slope_is_null_when_horizon_is_still_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "window_quality_audit.parquet")
            row_position = int(row_index_df.index[row_index_df["record.id"] == "r100"][0])
            self.assertTrue(bool(audit_df.loc[row_position, "sht.temp_c__3h_insufficient_history"]))
            self.assertTrue(bool(audit_df.loc[row_position, "sht.temp_c__8h_insufficient_history"]))
            self.assertTrue(pd.isna(feature_df.loc[row_position, "sht.temp_c__3h_slope_per_hour"]))
            self.assertTrue(pd.isna(feature_df.loc[row_position, "sht.temp_c__8h_slope_per_hour"]))

    def test_v2_time_span_coverage_blocks_warmup_rows_even_after_count_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "window_quality_audit.parquet")

            warmup_row = int(row_index_df.index[row_index_df["record.id"] == "r108"][0])
            early_8h_row = int(row_index_df.index[row_index_df["record.id"] == "r15"][0])

            self.assertEqual(int(audit_df.loc[warmup_row, "3h_valid_observation_count"]), 6)
            self.assertLess(float(audit_df.loc[warmup_row, "3h_span_coverage_ratio"]), 0.75)
            self.assertTrue(bool(audit_df.loc[warmup_row, "sht.temp_c__3h_insufficient_history"]))
            self.assertTrue(pd.isna(feature_df.loc[warmup_row, "sht.temp_c__3h_median"]))
            self.assertFalse(bool(audit_df.loc[warmup_row, "3h_eligible_for_training"]))

            self.assertEqual(int(audit_df.loc[early_8h_row, "8h_valid_observation_count"]), 15)
            self.assertLess(float(audit_df.loc[early_8h_row, "8h_span_coverage_ratio"]), 0.75)
            self.assertTrue(pd.isna(feature_df.loc[early_8h_row, "sht.temp_c__8h_median"]))

    def test_v2_continuity_break_resets_window_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            audit_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "window_quality_audit.parquet")
            row_position = int(row_index_df.index[row_index_df["record.id"] == "r100"][0])
            self.assertTrue(pd.isna(feature_df.loc[row_position, "sht.temp_c__3h_median"]))
            self.assertEqual(int(audit_df.loc[row_position, "3h_continuity_reset_count"]), 1)

    def test_v2_windows_never_cross_split_or_segment_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            split_row = int(row_index_df.index[row_index_df["record.id"] == "r104"][0])
            segment_row = int(row_index_df.index[row_index_df["record.id"] == "r200"][0])
            self.assertTrue(pd.isna(feature_df.loc[split_row, "sht.temp_c__3h_median"]))
            self.assertTrue(pd.isna(feature_df.loc[segment_row, "sht.temp_c__3h_median"]))

    def test_v2_future_observations_never_contribute_to_earlier_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            row_position = int(row_index_df.index[row_index_df["record.id"] == "r15"][0])
            self.assertAlmostEqual(feature_df.loc[row_position, "sht.temp_c__3h_median"], 29.0)

    def test_v2_quality_report_exposes_audit_summary_and_8h_features_materialize(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_window" / "X.parquet")
            quality_report = json.loads(
                (result.output_dir / "views" / "v2_sensor_window" / "quality_report.json").read_text(encoding="utf-8")
            )
            row_position = int(row_index_df.index[row_index_df["record.id"] == "r27"][0])
            self.assertFalse(pd.isna(feature_df.loc[row_position, "sht.temp_c__8h_median"]))
            self.assertIn("window_audit_summary", quality_report)
            self.assertIn("window_policy", quality_report)

    def test_v2_hashes_are_deterministic_for_identical_reruns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            output_root = Path(temp_dir) / "artifacts"

            first = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=output_root,
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )
            second = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=output_root,
                    mode="feature-only",
                    selected_views=("v2_sensor_window",),
                )
            )

            first_manifest = json.loads(
                (first.output_dir / "views" / "v2_sensor_window" / "manifest.json").read_text(encoding="utf-8")
            )
            second_manifest = json.loads(
                (second.output_dir / "views" / "v2_sensor_window" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first_manifest["source_canonical_hash"], second_manifest["source_canonical_hash"])
            self.assertEqual(first_manifest["source_schema_hash"], second_manifest["source_schema_hash"])
            self.assertEqual(first_manifest["feature_catalog_hash"], second_manifest["feature_catalog_hash"])
            self.assertEqual(first_manifest["view_configuration_hash"], second_manifest["view_configuration_hash"])
            self.assertEqual(first_manifest["ordered_feature_list_hash"], second_manifest["ordered_feature_list_hash"])
            self.assertEqual(first_manifest["x_data_hash"], second_manifest["x_data_hash"])


if __name__ == "__main__":
    unittest.main()
