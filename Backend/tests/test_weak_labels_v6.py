from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels import WeakLabelsConfig, build_weak_labels
from Backend.Benchmark.weak_labels.shared.configs import V6_BLOCK_MIN_COVERAGE_RATIO, V6_LOW_RUN_MIN_STEPS
from Backend.tests.dataset_views_helpers import create_dataset_views_v6_fixture


class WeakLabelsV6Tests(unittest.TestCase):
    def test_v6_event_and_block_contracts_hold_on_v6_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = build_weak_labels(
                WeakLabelsConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "weak_labels_artifacts",
                )
            )

            output_dir = result.output_dir
            point_dir = output_dir / "point"
            v6_dir = output_dir / "v6"
            registry_dir = output_dir / "registries"
            for path in (
                v6_dir / "v6_event_labels.parquet",
                v6_dir / "v6_b8_block_composition.parquet",
                v6_dir / "v6_b8_block_labels.parquet",
                v6_dir / "boundary_event_audit.parquet",
            ):
                self.assertTrue(path.exists(), str(path))

            point_flags_df = pd.read_parquet(point_dir / "point_evidence_flags.parquet")
            event_df = pd.read_parquet(v6_dir / "v6_event_labels.parquet")
            block_composition_df = pd.read_parquet(v6_dir / "v6_b8_block_composition.parquet")
            block_labels_df = pd.read_parquet(v6_dir / "v6_b8_block_labels.parquet")
            boundary_df = pd.read_parquet(v6_dir / "boundary_event_audit.parquet")
            dependency_df = pd.read_csv(registry_dir / "label_dependency_registry.csv")

            persistent_events = event_df.loc[event_df["label_name"].astype("string") == "persistent_low_relative_moisture_event"].copy()
            self.assertGreater(len(persistent_events), 0)
            point_lookup = point_flags_df.set_index(point_flags_df["record.id"].astype("string"))
            for row in persistent_events.to_dict(orient="records"):
                record_ids = json.loads(str(row["record_ids"]))
                self.assertGreaterEqual(len(record_ids), V6_LOW_RUN_MIN_STEPS)
                low_flags = point_lookup.loc[record_ids, "low_relative_moisture_flag"].fillna(False).astype(bool)
                self.assertTrue(low_flags.all())

            if not boundary_df.empty:
                self.assertTrue((~boundary_df["intrinsic_eligibility"].fillna(False).astype(bool)).all())

            joined_blocks = block_labels_df.merge(
                block_composition_df.loc[
                    :,
                    [
                        "sample_id",
                        "coverage_ratio",
                        "continuity_count",
                        "persistent_overlap_count",
                        "unknown_overlap_count",
                    ],
                ],
                on="sample_id",
                how="inner",
            )
            self.assertFalse(joined_blocks.empty)

            excluded_mask = (
                (joined_blocks["coverage_ratio"].astype(float) < V6_BLOCK_MIN_COVERAGE_RATIO)
                | (joined_blocks["continuity_count"].fillna(0).astype(int) > 1)
            )
            self.assertTrue(
                (
                    joined_blocks.loc[excluded_mask, "label_name"].astype("string")
                    == "insufficient_coverage_block"
                ).all()
            )

            mixed_mask = (
                (joined_blocks["persistent_overlap_count"].fillna(0).astype(int) > 0)
                & (joined_blocks["unknown_overlap_count"].fillna(0).astype(int) > 0)
                & (~excluded_mask)
            )
            if mixed_mask.any():
                self.assertTrue(
                    (
                        joined_blocks.loc[mixed_mask, "label_name"].astype("string")
                        == "unknown_or_mixed_environment_block"
                    ).all()
                )

            block_dependency = dependency_df.loc[
                dependency_df["task_id"].astype("string") == "v6_b8_block",
                "proxy_fields",
            ].astype("string")
            self.assertIn("v6_event_overlap", block_dependency.tolist())


if __name__ == "__main__":
    unittest.main()
