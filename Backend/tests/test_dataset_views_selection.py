from __future__ import annotations

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

    def test_current_run_does_not_materialize_removed_families(self) -> None:
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

            self.assertFalse((result.output_dir / "views" / "v3_direct").exists())
            self.assertFalse((result.output_dir / "views" / "v5_proxy_reduced").exists())
            self.assertFalse((result.output_dir / "views" / "v6_sequence_8h").exists())

    def test_semantic_view_names_are_unique(self) -> None:
        view_ids = [entry.semantic_view_id for entry in taxonomy_entries()]
        self.assertEqual(len(view_ids), len(set(view_ids)))

    def test_numeric_aliases_do_not_map_to_multiple_semantic_meanings(self) -> None:
        public_aliases = [entry.numeric_alias for entry in taxonomy_entries() if entry.public_selectable]
        self.assertEqual(len(public_aliases), len(set(public_aliases)))

    def test_removed_legacy_names_are_rejected_with_targeted_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Use 'v1_sensor_row'"):
            resolve_view_id("v1_full_sensor")
        with self.assertRaisesRegex(ValueError, "removed from the active benchmark surface"):
            resolve_view_id("v3_direct")
        with self.assertRaisesRegex(ValueError, "removed from the active benchmark surface"):
            resolve_view_id("v5_proxy_reduced")
        with self.assertRaisesRegex(ValueError, "removed from the active benchmark surface"):
            resolve_view_id("v6_event_level")

    def test_numeric_alias_resolves_to_semantic_name(self) -> None:
        self.assertEqual(resolve_view_id("v0"), "v0_minimal_sensor")
        self.assertEqual(resolve_view_id("v1"), "v1_sensor_row")

    def test_v2_alias_resolves_to_all_public_v2_views(self) -> None:
        self.assertEqual(
            resolve_view_ids(("v2",)),
            (
                "v2_minimal_sensor_window_3h",
                "v2_minimal_sensor_window_8h",
                "v2_sensor_row_window_3h",
                "v2_sensor_row_window_8h",
            ),
        )


if __name__ == "__main__":
    unittest.main()
