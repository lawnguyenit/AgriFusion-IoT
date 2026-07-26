from __future__ import annotations

import json
import unittest

import pandas as pd

from Backend.Benchmark.evaluation_protocols.pipeline.smoke_support import (
    build_pooled_prediction_summary,
    build_stage_run_frames,
)


class EvaluationProtocolSmokeSupportTests(unittest.TestCase):
    def test_build_stage_run_frames_uses_comparison_groups_for_same_y_stage(self) -> None:
        stage_spec = {
            "stage_id": "level_3_primary_matrix",
            "feature_views": ("v0_point", "v2_same_y_mini_3h", "v2_same_y_mini_8h"),
            "fold_ids": ("fold_01",),
            "comparison_ids": ("v0_vs_v2_mini_3h", "v0_vs_v2_mini_8h"),
        }
        comparison_training_manifest = pd.DataFrame(
            [
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "left",
                    "feature_view_id": "v0_point",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r1",
                    "record_id_order": 1,
                    "record_set_hash": "hash_3h",
                },
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "right",
                    "feature_view_id": "v2_same_y_mini_3h",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r1",
                    "record_id_order": 1,
                    "record_set_hash": "hash_3h",
                },
                {
                    "comparison_id": "v0_vs_v2_mini_8h",
                    "comparison_side": "left",
                    "feature_view_id": "v0_point",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r2",
                    "record_id_order": 1,
                    "record_set_hash": "hash_8h",
                },
                {
                    "comparison_id": "v0_vs_v2_mini_8h",
                    "comparison_side": "right",
                    "feature_view_id": "v2_same_y_mini_8h",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r2",
                    "record_id_order": 1,
                    "record_set_hash": "hash_8h",
                },
            ]
        ).convert_dtypes()

        run_frames, validation_rows = build_stage_run_frames(
            stage_spec=stage_spec,
            task_training_manifest=pd.DataFrame().convert_dtypes(),
            comparison_training_manifest=comparison_training_manifest,
        )

        self.assertEqual(len(run_frames), 4)
        self.assertEqual(
            {
                (str(row["comparison_id"]), str(row["comparison_side"]), str(row["feature_view_id"]))
                for row in run_frames
            },
            {
                ("v0_vs_v2_mini_3h", "left", "v0_point"),
                ("v0_vs_v2_mini_3h", "right", "v2_same_y_mini_3h"),
                ("v0_vs_v2_mini_8h", "left", "v0_point"),
                ("v0_vs_v2_mini_8h", "right", "v2_same_y_mini_8h"),
            },
        )
        self.assertTrue(all(bool(row["passed"]) for row in validation_rows))

    def test_build_stage_run_frames_flags_misaligned_comparison_order(self) -> None:
        stage_spec = {
            "stage_id": "level_2_v0_vs_v2_mini_3h_fold_01",
            "feature_views": ("v0_point", "v2_same_y_mini_3h"),
            "fold_ids": ("fold_01",),
            "comparison_ids": ("v0_vs_v2_mini_3h",),
        }
        comparison_training_manifest = pd.DataFrame(
            [
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "left",
                    "feature_view_id": "v0_point",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r1",
                    "record_id_order": 1,
                    "record_set_hash": "hash_a",
                },
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "left",
                    "feature_view_id": "v0_point",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r2",
                    "record_id_order": 2,
                    "record_set_hash": "hash_a",
                },
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "right",
                    "feature_view_id": "v2_same_y_mini_3h",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r2",
                    "record_id_order": 1,
                    "record_set_hash": "hash_a",
                },
                {
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "right",
                    "feature_view_id": "v2_same_y_mini_3h",
                    "fold_id": "fold_01",
                    "partition": "train",
                    "sample_id": "r1",
                    "record_id_order": 2,
                    "record_set_hash": "hash_a",
                },
            ]
        ).convert_dtypes()

        _, validation_rows = build_stage_run_frames(
            stage_spec=stage_spec,
            task_training_manifest=pd.DataFrame().convert_dtypes(),
            comparison_training_manifest=comparison_training_manifest,
        )

        alignment_row = next(
            row for row in validation_rows if str(row["scope"]).startswith("comparison_alignment::")
        )
        self.assertFalse(bool(alignment_row["passed"]))

    def test_build_pooled_prediction_summary_aggregates_across_folds(self) -> None:
        predictions_df = pd.DataFrame(
            [
                {
                    "stage_id": "level_3_primary_matrix",
                    "run_scope": "comparison",
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "left",
                    "feature_view_id": "v0_point",
                    "feature_source_view_id": "v0_minimal_sensor",
                    "fold_id": "fold_01",
                    "partition": "test",
                    "sample_id": "r1",
                    "label_name_true": "normal_point",
                    "label_name_pred": "normal_point",
                    "y_true_index": 0,
                    "y_pred_index": 0,
                    "class_names_json": json.dumps(["normal_point", "low_relative_moisture_point"]),
                },
                {
                    "stage_id": "level_3_primary_matrix",
                    "run_scope": "comparison",
                    "comparison_id": "v0_vs_v2_mini_3h",
                    "comparison_side": "left",
                    "feature_view_id": "v0_point",
                    "feature_source_view_id": "v0_minimal_sensor",
                    "fold_id": "fold_02",
                    "partition": "test",
                    "sample_id": "r2",
                    "label_name_true": "low_relative_moisture_point",
                    "label_name_pred": "low_relative_moisture_point",
                    "y_true_index": 1,
                    "y_pred_index": 1,
                    "class_names_json": json.dumps(["normal_point", "low_relative_moisture_point"]),
                },
            ]
        ).convert_dtypes()

        pooled = build_pooled_prediction_summary(predictions_df)

        self.assertEqual(len(pooled), 1)
        self.assertEqual(int(pooled.loc[0, "fold_count"]), 2)
        self.assertEqual(int(pooled.loc[0, "pooled_row_count"]), 2)
        self.assertEqual(float(pooled.loc[0, "accuracy"]), 1.0)
        self.assertEqual(float(pooled.loc[0, "supported_class_macro_f1"]), 1.0)
        self.assertEqual(float(pooled.loc[0, "fixed_ontology_macro_f1"]), 1.0)


if __name__ == "__main__":
    unittest.main()
