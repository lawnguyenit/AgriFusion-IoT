import unittest

import pandas as pd

from Backend.Benchmark.model_suite.analysis.unres_origin_prediction_join import (
    build_confusion_summary,
    build_joined_frame,
)


class UnresOriginPredictionJoinTests(unittest.TestCase):
    def test_joins_origins_and_reports_three_prediction_buckets(self) -> None:
        predictions = pd.DataFrame(
            [
                {"feature_view_id": "v2_temporal_mini_3h", "partition": "test", "sample_id": "k1", "label_name_true": "unresolved_environmental_evidence_at_anchor", "label_name_pred": "unresolved_environmental_evidence_at_anchor"},
                {"feature_view_id": "v2_temporal_mini_3h", "partition": "test", "sample_id": "k2", "label_name_true": "unresolved_environmental_evidence_at_anchor", "label_name_pred": "persistent_low_relative_moisture_at_anchor"},
                {"feature_view_id": "v2_temporal_mini_3h", "partition": "test", "sample_id": "a1", "label_name_true": "unresolved_environmental_evidence_at_anchor", "label_name_pred": "reference_context_at_anchor"},
                {"feature_view_id": "v2_temporal_mini_3h", "partition": "test", "sample_id": "a2", "label_name_true": "unresolved_environmental_evidence_at_anchor", "label_name_pred": "unresolved_environmental_evidence_at_anchor"},
            ]
        )
        origins = pd.DataFrame(
            [
                {"sample_id": "k1", "unres_origin": "UNRES_K", "temporal_label": "unresolved_environmental_evidence_at_anchor", "origin_formula": "M_t <= Q and d_t < K"},
                {"sample_id": "k2", "unres_origin": "UNRES_K", "temporal_label": "unresolved_environmental_evidence_at_anchor", "origin_formula": "M_t <= Q and d_t < K"},
                {"sample_id": "a1", "unres_origin": "UNRES_A", "temporal_label": "unresolved_environmental_evidence_at_anchor", "origin_formula": "M_t > Q and E_aux+"},
                {"sample_id": "a2", "unres_origin": "UNRES_A", "temporal_label": "unresolved_environmental_evidence_at_anchor", "origin_formula": "M_t > Q and E_aux+"},
            ]
        )

        joined = build_joined_frame(predictions, origins, feature_view_ids=("v2_temporal_mini_3h",), partitions=("test",))
        summary = build_confusion_summary(joined, feature_view_ids=("v2_temporal_mini_3h",), partitions=("test",))

        self.assertEqual(len(joined), 4)
        k_row = summary.loc[summary["true_origin"].eq("UNRES_K")].iloc[0]
        a_row = summary.loc[summary["true_origin"].eq("UNRES_A")].iloc[0]
        self.assertEqual((int(k_row["pred_low"]), int(k_row["pred_unres"]), int(k_row["pred_ref"])), (1, 1, 0))
        self.assertEqual((int(a_row["pred_low"]), int(a_row["pred_unres"]), int(a_row["pred_ref"])), (0, 1, 1))
        self.assertEqual(float(k_row["recall"]), 0.5)
        self.assertEqual(float(a_row["recall"]), 0.5)


if __name__ == "__main__":
    unittest.main()
