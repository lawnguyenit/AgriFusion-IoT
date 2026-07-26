from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from Backend.Benchmark.weak_labels import WeakLabelsConfig, build_weak_labels
from Backend.tests.dataset_views_helpers import create_dataset_views_v2_fixture


class WeakLabelsPointAndV2Tests(unittest.TestCase):
    def test_point_and_v2_contracts_hold_on_v2_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v2_fixture(Path(temp_dir))
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
            v2_dir = output_dir / "v2"
            registry_dir = output_dir / "registries"
            metadata_dir = output_dir / "run_metadata"
            for path in (
                point_dir / "point_evidence_flags.parquet",
                point_dir / "point_labels_detailed.parquet",
                point_dir / "point_labels_train.parquet",
                point_dir / "technical_labels_audit.parquet",
                v2_dir / "v2_same_y_labels.parquet",
                v2_dir / "v2_temporal_evidence_3h.parquet",
                v2_dir / "v2_temporal_evidence_8h.parquet",
                v2_dir / "v2_temporal_labels_3h.parquet",
                v2_dir / "v2_temporal_labels_8h.parquet",
                registry_dir / "label_dependency_registry.csv",
                metadata_dir / "run_manifest.json",
            ):
                self.assertTrue(path.exists(), str(path))

            point_train_df = pd.read_parquet(point_dir / "point_labels_train.parquet")
            point_detailed_df = pd.read_parquet(point_dir / "point_labels_detailed.parquet")
            v2_same_y_df = pd.read_parquet(v2_dir / "v2_same_y_labels.parquet")
            v2_evidence_3h_df = pd.read_parquet(v2_dir / "v2_temporal_evidence_3h.parquet")
            v2_evidence_8h_df = pd.read_parquet(v2_dir / "v2_temporal_evidence_8h.parquet")
            v2_temporal_3h_df = pd.read_parquet(v2_dir / "v2_temporal_labels_3h.parquet")
            v2_temporal_8h_df = pd.read_parquet(v2_dir / "v2_temporal_labels_8h.parquet")
            dependency_df = pd.read_csv(registry_dir / "label_dependency_registry.csv")

            v0_df = point_train_df.loc[point_train_df["task_id"].astype("string") == "v0_point_train", ["sample_id", "label_name", "label_status"]]
            v1_df = point_train_df.loc[point_train_df["task_id"].astype("string") == "v1_point_train", ["sample_id", "label_name", "label_status"]]
            point_join = v0_df.merge(v1_df, on="sample_id", how="inner", suffixes=("_v0", "_v1"))
            self.assertFalse(point_join.empty)
            self.assertTrue((point_join["label_name_v0"].astype("string") == point_join["label_name_v1"].astype("string")).all())
            self.assertTrue((point_join["label_status_v0"].astype("string") == point_join["label_status_v1"].astype("string")).all())

            point_lookup = v0_df.rename(columns={"label_name": "point_label_name", "label_status": "point_label_status"})
            for task_id in ("v2_same_y_3h", "v2_same_y_8h"):
                same_y_task_df = v2_same_y_df.loc[v2_same_y_df["task_id"].astype("string") == task_id].copy()
                joined = same_y_task_df.merge(point_lookup, on="sample_id", how="inner")
                eligible = joined["intrinsic_eligibility"].fillna(False).astype(bool)
                self.assertTrue(
                    (
                        joined.loc[eligible, "label_name"].astype("string")
                        == joined.loc[eligible, "point_label_name"].astype("string")
                    ).all()
                )
                self.assertTrue(joined.loc[~eligible, "label_name"].isna().all())

            invalid_point = point_detailed_df.loc[point_detailed_df["sample_id"].astype("string") == "r8"].iloc[0]
            self.assertEqual(str(invalid_point["label_name"]), "excluded_technical_invalid")
            self.assertFalse(bool(invalid_point["intrinsic_eligibility"]))

            self._assert_v2_temporal_contract(v2_temporal_3h_df, v2_evidence_3h_df)
            self._assert_v2_temporal_contract(v2_temporal_8h_df, v2_evidence_8h_df)

            direct_source_rows = dependency_df.loc[dependency_df["task_id"].astype("string") == "v0_point_train", "direct_source_fields"]
            direct_source_text = "|".join(str(value) for value in direct_source_rows.tolist())
            self.assertNotIn("ph", direct_source_text.lower())
            self.assertNotIn("n_proxy", direct_source_text.lower())
            self.assertNotIn("p_proxy", direct_source_text.lower())
            self.assertNotIn("k_proxy", direct_source_text.lower())

    def _assert_v2_temporal_contract(self, labels_df: pd.DataFrame, evidence_df: pd.DataFrame) -> None:
        joined = labels_df.merge(
            evidence_df.loc[
                :,
                [
                    "record.id",
                    "eligible_for_training",
                    "intrinsic_eligibility",
                    "low_run_length_ending_at_point",
                    "point_train_label_name",
                    "positive_environmental_evidence_count",
                ],
            ].rename(columns={"record.id": "sample_id", "intrinsic_eligibility": "evidence_intrinsic_eligibility"}),
            on="sample_id",
            how="inner",
        )
        self.assertFalse(joined.empty)

        excluded = ~joined["intrinsic_eligibility"].fillna(False).astype(bool)
        self.assertTrue((joined.loc[excluded, "label_name"].astype("string") == "insufficient_window_context").all())

        persistent = joined["label_name"].astype("string") == "persistent_low_relative_moisture_window"
        if persistent.any():
            self.assertTrue((joined.loc[persistent, "point_train_label_name"].astype("string") == "low_relative_moisture_point").all())
            self.assertTrue((joined.loc[persistent, "low_run_length_ending_at_point"].fillna(0).astype(int) >= 3).all())

        unknown = joined["label_name"].astype("string") == "unknown_environment_window"
        if unknown.any():
            allowed = (
                (joined.loc[unknown, "point_train_label_name"].astype("string") == "unknown_environment_point")
                | (joined.loc[unknown, "positive_environmental_evidence_count"].fillna(0).astype(int) > 0)
            )
            self.assertTrue(allowed.all())


if __name__ == "__main__":
    unittest.main()
