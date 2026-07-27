from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from Backend.Benchmark.dataset_views.contracts import MaterializationConfig
from Backend.Benchmark.dataset_views.pipelines import materialize_dataset_views
from Backend.tests.dataset_views_helpers import create_dataset_views_v6_fixture


class DatasetViewsV6EnvironmentalTests(unittest.TestCase):
    def test_v6_sequence_materializes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            v6_dir = result.output_dir / "V6"
            self.assertTrue((result.output_dir / "views" / "v6_sequence_8h" / "manifest.json").exists())
            for name in (
                "dataset_manifest.json",
                "sequence_rows.parquet",
                "sequence_rows.csv",
                "chunk_manifest.csv",
                "discarded_chunks.csv",
                "event_fragment_registry.csv",
                "original_event_distribution.csv",
                "day_distribution.csv",
                "chunk_distribution.csv",
                "split_group_manifest.csv",
                "original_event_integrity.json",
                "threshold_manifest.json",
                "X.parquet",
                "y.parquet",
                "sequence_index.parquet",
                "auxiliary_features.parquet",
                "V6_audit_report.md",
            ):
                self.assertTrue((v6_dir / name).exists(), name)

    def test_v6_resampling_creates_v6_only_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            canonical_df = pd.read_csv(fixture["canonical_path"])
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            sequence_rows_df = pd.read_parquet(result.output_dir / "V6" / "sequence_rows.parquet")
            self.assertGreater(len(sequence_rows_df), len(canonical_df))
            synthetic_rows = sequence_rows_df.loc[sequence_rows_df["sequence.source_record_id"].isna()]
            self.assertGreater(len(synthetic_rows), 0)
            self.assertTrue(synthetic_rows["sequence.interpolated_mask"].fillna(False).any())

    def test_v6_discard_chunk_with_continuity_break(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            chunk_manifest_df = pd.read_csv(result.output_dir / "V6" / "chunk_manifest.csv")
            discarded = chunk_manifest_df.loc[chunk_manifest_df["discard_reason"] == "continuity_break"]
            self.assertGreater(len(discarded), 0)
            self.assertFalse(discarded["chunk_kept"].any())

    def test_v6_train_labels_use_three_class_taxonomy_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            y_df = pd.read_parquet(result.output_dir / "V6" / "y.parquet")
            self.assertEqual(
                set(y_df["final_train_label"].astype(str).unique()),
                {
                    "normal",
                    "persistent_low_relative_moisture_event",
                    "unknown_environment_event",
                },
            )

    def test_v6_short_runs_map_to_unknown_but_preserve_online_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            sequence_index_df = pd.read_parquet(result.output_dir / "V6" / "sequence_index.parquet")
            isolated = sequence_index_df.loc[
                sequence_index_df["detailed_event_type"].astype(str) == "isolated_unknown_anomaly"
            ]
            self.assertGreater(len(isolated), 0)
            self.assertTrue((isolated["final_train_label"].astype(str) == "unknown_environment_event").all())
            self.assertTrue((isolated["online_stage"].astype(str) == "isolated").all())

    def test_v6_low_moisture_run_backfills_from_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            sequence_index_df = pd.read_parquet(result.output_dir / "V6" / "sequence_index.parquet")
            low_moisture = sequence_index_df.loc[
                sequence_index_df["final_train_label"].astype(str) == "persistent_low_relative_moisture_event"
            ]
            self.assertGreater(len(low_moisture), 0)
            first_event = low_moisture.loc[low_moisture["event_id"] == low_moisture.iloc[0]["event_id"]]
            self.assertEqual(first_event["online_stage"].astype(str).tolist()[:3], ["isolated", "attention", "confirmed"])
            self.assertTrue((first_event["detailed_event_type"].astype(str) == "persistent_low_relative_moisture_event").all())

    def test_v6_other_confirmed_subtypes_still_train_as_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            sequence_index_df = pd.read_parquet(result.output_dir / "V6" / "sequence_index.parquet")
            thermal_rows = sequence_index_df.loc[
                sequence_index_df["detailed_event_type"].astype(str) == "thermal_dry_air_event_candidate"
            ]
            self.assertGreater(len(thermal_rows), 0)
            self.assertTrue((thermal_rows["final_train_label"].astype(str) == "unknown_environment_event").all())

    def test_v6_cross_chunk_fragments_are_marked_without_merging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            fragments_df = pd.read_csv(result.output_dir / "V6" / "event_fragment_registry.csv")
            boundary_fragments = fragments_df.loc[fragments_df["crosses_chunk_boundary"].fillna(False)]
            self.assertGreater(len(boundary_fragments), 0)
            self.assertTrue(
                (boundary_fragments["fragment_at_chunk_start"].fillna(False) | boundary_fragments["fragment_at_chunk_end"].fillna(False)).all()
            )

    def test_v6_original_event_ids_do_not_cross_continuity_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            sequence_rows_df = pd.read_parquet(result.output_dir / "V6" / "sequence_rows.parquet")
            event_rows = sequence_rows_df.loc[sequence_rows_df["original_event_id"].notna()].copy()
            grouped = (
                event_rows.groupby("original_event_id", dropna=False)
                .agg(
                    continuity_count=("continuity_segment_id", "nunique"),
                    candidate_type_count=("candidate_event_type", "nunique"),
                    detailed_type_count=("detailed_event_type", "nunique"),
                    final_label_count=("final_train_label", "nunique"),
                )
                .reset_index()
            )
            self.assertTrue((grouped["continuity_count"] == 1).all())
            self.assertTrue((grouped["candidate_type_count"] == 1).all())
            self.assertTrue((grouped["detailed_type_count"] == 1).all())
            self.assertTrue((grouped["final_label_count"] == 1).all())
            self.assertFalse(event_rows["candidate_priority_reason"].isna().any())

    def test_v6_target_loss_mask_uses_observed_timesteps_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            sequence_index_df = pd.read_parquet(result.output_dir / "V6" / "sequence_index.parquet")
            observed_mask = sequence_index_df["sequence.source_record_id"].notna()
            target_loss_mask = sequence_index_df["target_loss_mask"].fillna(False)
            self.assertTrue((target_loss_mask == observed_mask).all())
            interpolated_rows = sequence_index_df.loc[sequence_index_df["sequence.source_record_id"].isna()]
            self.assertGreater(len(interpolated_rows), 0)
            self.assertFalse(interpolated_rows["target_loss_mask"].fillna(False).any())

    def test_v6_reports_distribution_by_event_day_chunk_and_split_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            event_dist = pd.read_csv(result.output_dir / "V6" / "original_event_distribution.csv")
            day_dist = pd.read_csv(result.output_dir / "V6" / "day_distribution.csv")
            chunk_dist = pd.read_csv(result.output_dir / "V6" / "chunk_distribution.csv")
            split_groups = pd.read_csv(result.output_dir / "V6" / "split_group_manifest.csv")
            integrity = json.loads((result.output_dir / "V6" / "original_event_integrity.json").read_text(encoding="utf-8"))

            self.assertGreater(len(event_dist), 0)
            self.assertGreater(len(day_dist), 0)
            self.assertGreater(len(chunk_dist), 0)
            self.assertGreater(len(split_groups), 0)
            self.assertEqual(integrity["issue_count"], 0)
            event_split_groups = split_groups.loc[split_groups["split_group_kind"] == "original_event"]
            self.assertGreater(len(event_split_groups), 0)
            self.assertTrue((event_split_groups["split_group_id"] == event_split_groups["original_event_id"]).all())

    def test_v6_x_excludes_sensor_and_system_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            x_df = pd.read_parquet(result.output_dir / "V6" / "X.parquet")
            blocked = {
                "sht.read_ok",
                "npk.read_ok",
                "sht.valid",
                "npk.valid",
                "record.gap_flag",
                "delivery.is_buffered_replay",
                "network.gprs",
                "device.reset_or_power_on",
            }
            self.assertTrue(blocked.isdisjoint(set(x_df.columns)))
            self.assertTrue(
                {
                    "npk.soil_moisture_pct",
                    "npk.soil_temp_c",
                    "npk.ec",
                    "sht.temp_c",
                    "sht.humidity_pct",
                    "derived.vpd_kpa",
                    "sequence.observed_mask",
                    "sequence.interpolated_mask",
                    "sequence.missing_mask",
                    "sequence.time_since_last_observation_sec",
                }.issubset(set(x_df.columns))
            )

    def test_v6_hashes_are_deterministic_for_identical_reruns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            output_root = Path(temp_dir) / "artifacts"
            first = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=output_root,
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )
            second = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=output_root,
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            first_manifest = json.loads((first.output_dir / "V6" / "dataset_manifest.json").read_text(encoding="utf-8"))
            second_manifest = json.loads((second.output_dir / "V6" / "dataset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(first_manifest["source_canonical_hash"], second_manifest["source_canonical_hash"])
            self.assertEqual(first_manifest["source_schema_hash"], second_manifest["source_schema_hash"])
            self.assertEqual(first_manifest["feature_catalog_hash"], second_manifest["feature_catalog_hash"])
            self.assertEqual(first_manifest["sequence_rows_hash"], second_manifest["sequence_rows_hash"])
            self.assertEqual(first_manifest["x_hash"], second_manifest["x_hash"])
            self.assertEqual(first_manifest["y_hash"], second_manifest["y_hash"])

    def test_v6_outputs_preserve_nan_and_no_infinite_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = create_dataset_views_v6_fixture(Path(temp_dir))
            result = materialize_dataset_views(
                MaterializationConfig(
                    canonical_history_path=fixture["canonical_path"],
                    feature_catalog_path=fixture["catalog_path"],
                    manifest_path=fixture["manifest_path"],
                    output_root=Path(temp_dir) / "artifacts",
                    mode="feature-only",
                    selected_views=("v6",),
                )
            )

            x_df = pd.read_parquet(result.output_dir / "V6" / "X.parquet")
            numeric = x_df.select_dtypes(include=["number", "floating", "integer"]).to_numpy(dtype="float64", copy=False)
            self.assertFalse(np.isinf(numeric).any())


if __name__ == "__main__":
    unittest.main()
