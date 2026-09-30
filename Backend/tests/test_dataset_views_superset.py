from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.tests.dataset_views_helpers import create_dataset_views_v2_fixture


class DatasetViewsSupersetTests(unittest.TestCase):
    def test_superset_has_values_and_window_groups_with_identity_and_legacy_views(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v0_minimal_sensor", "v2_sensor_row_window_3h"),
                )
            )
            shared = result.output_dir / "shared"
            master = pd.read_parquet(shared / "feature_superset.parquet")
            registry = json.loads((shared / "feature_group_registry.json").read_text(encoding="utf-8"))
            source_manifest = json.loads((shared / "source_manifest.json").read_text(encoding="utf-8"))
            row_index = pd.read_parquet(shared / "row_index.parquet")

            self.assertEqual(master["sample_id"].astype("string").tolist(), row_index["record.id"].astype("string").tolist())
            self.assertEqual(master["source_row_position"].tolist(), list(range(len(row_index))))
            self.assertIn("npk.ec", registry["feature_groups"]["values"]["columns"])
            self.assertTrue(any(name.startswith("npk.ec__3h_") for name in registry["feature_groups"]["window_3h"]["columns"]))
            self.assertTrue(registry["feature_groups"]["values"]["columns_hash"])
            self.assertTrue(registry["matrix_schema_hash"])
            self.assertNotIn("window_8h", registry["feature_groups"])
            self.assertEqual(registry["row_count"], len(row_index))
            self.assertEqual(source_manifest["feature_superset"]["matrix_path"], str((shared / "feature_superset.parquet").resolve()))
            self.assertTrue((result.output_dir / "views" / "v0_minimal_sensor" / "X.parquet").is_file())
            self.assertTrue((result.output_dir / "views" / "v2_sensor_row_window_3h" / "X.parquet").is_file())


if __name__ == "__main__":
    unittest.main()
