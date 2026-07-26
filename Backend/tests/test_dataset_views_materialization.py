from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.api.types import is_float_dtype

from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.tests.dataset_views_helpers import create_dataset_views_fixture, create_dataset_views_v2_fixture


class DatasetViewsMaterializationTests(unittest.TestCase):
    def test_row_alignment_across_shared_v0_and_v1(self) -> None:
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

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            metadata_df = pd.read_parquet(result.output_dir / "shared" / "metadata.parquet")
            v0_df = pd.read_parquet(result.output_dir / "views" / "v0_minimal_sensor" / "X.parquet")
            v1_df = pd.read_parquet(result.output_dir / "views" / "v1_sensor_row" / "X.parquet")
            self.assertEqual(len(row_index_df), len(metadata_df))
            self.assertEqual(len(row_index_df), len(v0_df))
            self.assertEqual(len(row_index_df), len(v1_df))

    def test_metadata_separation_and_feature_only_outputs(self) -> None:
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

            metadata_df = pd.read_parquet(result.output_dir / "shared" / "metadata.parquet")
            feature_df = pd.read_parquet(result.output_dir / "views" / "v1_sensor_row" / "X.parquet")
            self.assertTrue(set(metadata_df.columns).isdisjoint(feature_df.columns))
            self.assertFalse((result.output_dir / "shared" / "labels.parquet").exists())
            self.assertTrue((result.output_dir / "shared" / "row_index.csv").exists())
            self.assertTrue((result.output_dir / "shared" / "metadata.csv").exists())
            self.assertTrue((result.output_dir / "views" / "v1_sensor_row" / "X.csv").exists())

            source_manifest = json.loads((result.output_dir / "shared" / "source_manifest.json").read_text(encoding="utf-8"))
            view_manifest = json.loads(
                (result.output_dir / "views" / "v1_sensor_row" / "manifest.json").read_text(encoding="utf-8")
            )
            feature_columns = json.loads(
                (result.output_dir / "views" / "v1_sensor_row" / "feature_columns.json").read_text(encoding="utf-8")
            )
            row_index_contract = json.loads(
                (result.output_dir / "shared" / "row_index_contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(source_manifest["label_status"], "not_attached")
            self.assertEqual(view_manifest["label_status"], "not_attached")
            self.assertEqual(source_manifest["materialized_public_views"], ["v1_sensor_row"])
            self.assertIn("v5_proxy_reduced_draft", source_manifest["materialized_nonpublic_drafts"])
            self.assertIn("debug_csv_paths", view_manifest)
            self.assertIn("pipeline_code_commit", source_manifest["source"])
            self.assertIn("materialization_config_hash", source_manifest["source"])
            self.assertIn("shared_artifacts", source_manifest)
            self.assertEqual(row_index_contract["artifact_name"], "row_index")
            self.assertEqual(feature_columns["identifier_columns"], ["record.id", "source_row_position"])
            self.assertEqual(feature_columns["allowed_feature_columns"], view_manifest["ordered_feature_list"])
            self.assertEqual(view_manifest["sample_id_hash"], row_index_contract["record_id_hash"])
            self.assertEqual(view_manifest["row_index_hash"], row_index_contract["file_hash"])
            self.assertEqual(view_manifest["feature_generator_code_commit"], source_manifest["source"]["pipeline_code_commit"])
            self.assertEqual(view_manifest["materialization_config_hash"], source_manifest["source"]["materialization_config_hash"])

    def test_null_and_dtype_preservation(self) -> None:
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
            self.assertTrue(pd.isna(dataframe.loc[1, "npk.ec"]))
            self.assertTrue(is_float_dtype(dataframe["npk.ec"]))

    def test_deterministic_source_and_configuration_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            output_root = Path(temp_dir) / "artifacts"

            first = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=output_root,
                    mode="feature-only",
                    selected_views=("v1_sensor_row",),
                )
            )
            second = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=output_root,
                    mode="feature-only",
                    selected_views=("v1_sensor_row",),
                )
            )

            first_manifest = json.loads(
                (first.output_dir / "views" / "v1_sensor_row" / "manifest.json").read_text(encoding="utf-8")
            )
            second_manifest = json.loads(
                (second.output_dir / "views" / "v1_sensor_row" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first_manifest["source_canonical_hash"], second_manifest["source_canonical_hash"])
            self.assertEqual(first_manifest["source_schema_hash"], second_manifest["source_schema_hash"])
            self.assertEqual(first_manifest["feature_catalog_hash"], second_manifest["feature_catalog_hash"])
            self.assertEqual(first_manifest["view_configuration_hash"], second_manifest["view_configuration_hash"])
            self.assertEqual(first_manifest["dependency_registry_hash"], second_manifest["dependency_registry_hash"])
            self.assertEqual(first_manifest["ordered_feature_list_hash"], second_manifest["ordered_feature_list_hash"])
            self.assertEqual(first_manifest["x_data_hash"], second_manifest["x_data_hash"])

    def test_v0_and_v1_mask_invalid_npk_measurements_consistently_with_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v0_minimal_sensor", "v1_sensor_row", "v2_sensor_row_window_3h"),
                )
            )

            row_index_df = pd.read_parquet(result.output_dir / "shared" / "row_index.parquet")
            v0_df = pd.read_parquet(result.output_dir / "views" / "v0_minimal_sensor" / "X.parquet")
            v1_df = pd.read_parquet(result.output_dir / "views" / "v1_sensor_row" / "X.parquet")
            v2_df = pd.read_parquet(result.output_dir / "views" / "v2_sensor_row_window_3h" / "X.parquet")

            invalid_row = int(row_index_df.index[row_index_df["record.id"] == "r8"][0])
            self.assertTrue(pd.isna(v0_df.loc[invalid_row, "npk.ec"]))
            for column in ("npk.soil_temp_c", "npk.soil_moisture_pct", "npk.ec", "npk.ph", "npk.n_proxy", "npk.p_proxy", "npk.k_proxy"):
                self.assertTrue(pd.isna(v1_df.loc[invalid_row, column]), column)
                self.assertTrue(pd.isna(v2_df.loc[invalid_row, column]), column)
                self.assertTrue(
                    pd.isna(v1_df.loc[invalid_row, column]) == pd.isna(v2_df.loc[invalid_row, column]),
                    column,
                )


if __name__ == "__main__":
    unittest.main()
