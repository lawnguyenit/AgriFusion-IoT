from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Backend.Benchmark.dataset_views.contracts import LabelConfig, MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.tests.dataset_views_helpers import create_dataset_views_fixture


class DatasetViewsLabelModeTests(unittest.TestCase):
    def test_benchmark_ready_requires_explicit_label_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "requires an explicit label artifact"):
                materialize_dataset_views(
                    MaterializationConfig(
                        canonical_history_path=fixture["canonical_path"],
                        feature_catalog_path=fixture["catalog_path"],
                        manifest_path=fixture["manifest_path"],
                        output_root=Path(temp_dir) / "artifacts",
                        mode="benchmark-ready",
                        selected_views=("v0_minimal_sensor",),
                    )
                )

    def test_benchmark_ready_rejects_label_artifact_without_record_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_fixture(Path(temp_dir))
            bad_labels = Path(temp_dir) / "bad_labels.csv"
            bad_labels.write_text("wrong_key,label_binary\nx,1\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "must contain key column 'record.id'"):
                materialize_dataset_views(
                    MaterializationConfig(
                        canonical_history_path=fixture["canonical_path"],
                        feature_catalog_path=fixture["catalog_path"],
                        manifest_path=fixture["manifest_path"],
                        output_root=Path(temp_dir) / "artifacts",
                        mode="benchmark-ready",
                        selected_views=("v0_minimal_sensor",),
                        label_config=LabelConfig(
                            artifact_path=bad_labels,
                            required_columns=("label_binary",),
                        ),
                    )
                )


if __name__ == "__main__":
    unittest.main()
