from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.configs import resolve_view_id, resolve_view_ids, taxonomy_entries
from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.tests.dataset_views_helpers import create_dataset_views_fixture


class DatasetViewsSelectionTests(unittest.TestCase):
    def test_v0_exact_feature_membership(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v0_minimal_sensor",),
                )
            )

            dataframe = pd.read_parquet(result.output_dir / "views" / "v0_minimal_sensor" / "X.parquet")
            self.assertEqual(
                dataframe.columns.tolist(),
                [
                    "sht.temp_c",
                    "sht.humidity_pct",
                    "npk.soil_temp_c",
                    "npk.soil_moisture_pct",
                    "npk.ec",
                    "npk.ph",
                    "npk.n_proxy",
                    "npk.p_proxy",
                    "npk.k_proxy",
                ],
            )

    def test_v1_exact_feature_membership(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v1_sensor_row",),
                )
            )

            dataframe = pd.read_parquet(result.output_dir / "views" / "v1_sensor_row" / "X.parquet")
            self.assertEqual(
                dataframe.columns.tolist(),
                [
                    "sht.temp_c",
                    "sht.humidity_pct",
                    "npk.soil_temp_c",
                    "npk.soil_moisture_pct",
                    "npk.ec",
                ],
            )

    def test_v1_contains_no_extra_measurement_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v1_sensor_row",),
                )
            )

            dataframe = pd.read_parquet(result.output_dir / "views" / "v1_sensor_row" / "X.parquet")
            self.assertTrue({"npk.ph", "npk.n_proxy", "npk.p_proxy", "npk.k_proxy"}.isdisjoint(dataframe.columns))

    def test_v1_contains_no_diagnostic_or_metadata_fields(self) -> None:
        blocked = {
            "sht.packet_present",
            "sht.read_ok",
            "sht.sample_valid",
            "sht.retry_count",
            "sht.read_elapsed_ms",
            "npk.packet_present",
            "npk.read_ok",
            "npk.sample_valid",
            "npk.error_code_raw",
            "npk.crc_ok",
            "npk.frame_ok",
            "npk.signal_present",
            "npk.values_valid",
            "npk.retry_count",
            "npk.consecutive_fail_count",
            "npk.read_duration_ms",
            "record.id",
            "record.ts_sample",
            "record.segment_id",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v1_sensor_row",),
                )
            )

            dataframe = pd.read_parquet(result.output_dir / "views" / "v1_sensor_row" / "X.parquet")
            self.assertTrue(blocked.isdisjoint(dataframe.columns))

    def test_current_run_does_not_materialize_proxy_reduced_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v0_minimal_sensor", "v1_sensor_row"),
                )
            )

            self.assertFalse((result.output_dir / "views" / "v6_event_level").exists())
            self.assertFalse((result.output_dir / "views" / "v5_proxy_reduced_draft").exists())

    def test_semantic_view_names_are_unique(self) -> None:
        view_ids = [entry.semantic_view_id for entry in taxonomy_entries()]
        self.assertEqual(len(view_ids), len(set(view_ids)))

    def test_numeric_aliases_do_not_map_to_multiple_semantic_meanings(self) -> None:
        public_aliases = [
            entry.numeric_alias
            for entry in taxonomy_entries()
            if entry.public_selectable
        ]
        self.assertEqual(len(public_aliases), len(set(public_aliases)))

    def test_legacy_names_are_rejected_with_targeted_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Use 'v1_sensor_row'"):
            resolve_view_id("v1_full_sensor")
        with self.assertRaisesRegex(ValueError, "No current public replacement exists"):
            resolve_view_id("v6_proxy_reduced")
        with self.assertRaisesRegex(ValueError, "Use 'v6_sequence_8h'"):
            resolve_view_id("v6_event_level")
        with self.assertRaisesRegex(ValueError, "single 8-hour sequence dataset"):
            resolve_view_id("v6b_continuous_sequence")

    def test_numeric_alias_resolves_to_semantic_name(self) -> None:
        self.assertEqual(resolve_view_id("v0"), "v0_minimal_sensor")
        self.assertEqual(resolve_view_id("v1"), "v1_sensor_row")
        self.assertEqual(resolve_view_id("v6"), "v6_sequence_8h")

    def test_v6_family_token_expands_to_all_subviews(self) -> None:
        self.assertEqual(
            resolve_view_ids(("v6",)),
            ("v6_sequence_8h",),
        )

    def test_v2_alias_resolves_only_primary_3h_views(self) -> None:
        self.assertEqual(
            resolve_view_ids(("v2",)),
            ("v2_minimal_sensor_window_3h", "v2_sensor_row_window_3h"),
        )


if __name__ == "__main__":
    unittest.main()
