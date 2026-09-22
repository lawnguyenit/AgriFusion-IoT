import unittest

import numpy as np
import pandas as pd

from Backend.Benchmark.model_suite.analysis.k_window_variants.configured_runner import build_configured_variants
from Backend.Benchmark.model_suite.analysis.k_window_variants.history import FeatureBundle, build_causal_history_bundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.embedding import build_causal_sequence_bundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.representations import build_representation_bundles
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_features import build_history_audit_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.semantic_runner import _depth_bin, _provenance_stratum


class KHistorySemanticsTests(unittest.TestCase):
    def test_ordered_lag_features_use_only_strictly_past_rows(self):
        ids = ["a", "b", "c"]
        snapshot = pd.DataFrame({"sample_id": ids, "m": [1.0, 2.0, 3.0]})
        window = pd.DataFrame({"sample_id": ids, "m": [1.0, 2.0, 3.0], "m__3h_median": [1.0, 1.5, 2.0]})
        row_index = pd.DataFrame({
            "record.id": ids,
            "record.node_id": ["N"] * 3,
            "record.segment_id": ["S"] * 3,
            "record.ts_sample": [1000, 2000, 3000],
            "source_row_position": [0, 1, 2],
        })
        bundle = build_causal_history_bundle(
            snapshot_frame=snapshot,
            snapshot_feature_names=["m"],
            window_frame=window,
            window_feature_names=["m", "m__3h_median"],
            row_index=row_index,
            max_lags=2,
        )
        frame = bundle.frame.set_index("sample_id")
        self.assertTrue(pd.isna(frame.loc["a", "m__causal_lag_1"]))
        self.assertEqual(frame.loc["b", "m__causal_lag_1"], 1.0)
        self.assertEqual(frame.loc["c", "m__causal_lag_1"], 2.0)
        self.assertEqual(frame.loc["c", "m__causal_lag_2"], 1.0)
        self.assertEqual(frame.loc["c", "causal_history__3h_prior_row_count"], 2.0)

    def test_k_provenance_strata_are_separate_from_model_labels(self):
        row = {
            "label_online": "unresolved_environmental_evidence_at_anchor",
            "unres_origin": "UNRES_K",
            "support_depth_at_anchor": 1,
            "eventual_run_length": 3,
        }
        self.assertEqual(_provenance_stratum(row), "U_K_succ")
        row["eventual_run_length"] = 2
        self.assertEqual(_provenance_stratum(row), "U_K_fail")
        self.assertEqual(_depth_bin(1), "d=1")
        self.assertEqual(_depth_bin(3), "d>=3")

    def test_causal_sequence_ends_at_anchor_and_excludes_future_rows(self):
        ids = ["a", "b", "c", "d"]
        snapshot = pd.DataFrame({"sample_id": ids, "m": [10.0, 20.0, 30.0, 40.0]})
        row_index = pd.DataFrame({
            "record.id": ids,
            "record.node_id": ["N"] * 4,
            "record.segment_id": ["S"] * 4,
            "record.ts_sample": [1000, 2000, 3000, 4000],
            "source_row_position": [0, 1, 2, 3],
        })
        bundle = build_causal_sequence_bundle(
            snapshot_frame=snapshot,
            feature_names=["m"],
            row_index=row_index,
            sequence_length=3,
        )
        anchor_b = bundle.values[bundle.sample_ids.index("b"), :, 0]
        anchor_c = bundle.values[bundle.sample_ids.index("c"), :, 0]
        self.assertTrue(np.isnan(anchor_b[0]))
        np.testing.assert_array_equal(anchor_b[1:], np.array([10.0, 20.0], dtype=np.float32))
        np.testing.assert_array_equal(anchor_c, np.array([10.0, 20.0, 30.0], dtype=np.float32))
        self.assertEqual(bundle.row_mask[bundle.sample_ids.index("b")].tolist(), [False, True, True])

    def test_r_representation_contract_and_schedule_are_explicit(self):
        sample_ids = ["a", "b"]
        snapshot_names = [f"sensor_{index}" for index in range(9)]
        summary_names = [f"sensor_{index}__3h_stat_{stat}" for index in range(9) for stat in range(5)]
        lag_names = [f"sensor_{index}__causal_lag_{lag}" for index in range(9) for lag in range(1, 13)]
        ordered_names = lag_names + [f"causal_history__lag_{lag}_age_hours" for lag in range(1, 13)] + [f"causal_history__quality_{index}" for index in range(5)]
        snapshot_frame = pd.DataFrame([[sample_id, *range(9)] for sample_id in sample_ids], columns=["sample_id", *snapshot_names])
        window_frame = pd.concat([snapshot_frame, pd.DataFrame([[1] * 45, [2] * 45], columns=summary_names)], axis=1)
        history_frame = pd.concat([window_frame, pd.DataFrame([[1] * 125, [2] * 125], columns=ordered_names)], axis=1)
        snapshot_bundle = FeatureBundle(snapshot_frame, snapshot_names, {"representation": "snapshot"})
        window_bundle = FeatureBundle(window_frame, [*snapshot_names, *summary_names], {"representation": "window"})
        history_bundle = FeatureBundle(history_frame, [*snapshot_names, *summary_names, *ordered_names], {"representation": "history"})
        representations = build_representation_bundles(
            snapshot_bundle=snapshot_bundle,
            window_bundle=window_bundle,
            history_bundle=history_bundle,
        )
        self.assertEqual({key: len(value.feature_bundle.feature_names) for key, value in representations.items()}, {
            "R00": 9,
            "R10": 54,
            "R01": 134,
            "R11": 179,
        })
        variants = build_configured_variants(representations=representations)
        self.assertEqual(len(variants), 10)
        self.assertEqual([variant.variant_id for variant in variants[:2]], ["k1_R00", "k1_R11"])
        self.assertEqual(sum(variant.k == 3 and variant.target_view_id.endswith("online_3h") for variant in variants), 4)
        self.assertEqual(sum(variant.k == 3 and variant.target_view_id.endswith("event_3h") for variant in variants), 4)

    def test_history_audit_separates_sensor_lags_from_metadata_and_preserves_disruption_dimension(self):
        sample_ids = ["a", "b"]
        snapshot_names = [f"sensor_{index}" for index in range(9)]
        summary_names = [f"sensor_{index}__3h_stat_{stat}" for index in range(9) for stat in range(5)]
        lag_names = [f"sensor_{index}__causal_lag_{lag}" for lag in range(1, 13) for index in range(9)]
        age_names = [f"causal_history__lag_{lag}_age_hours" for lag in range(1, 13)]
        quality_names = [f"causal_history__3h_quality_{index}" for index in range(5)]
        snapshot_frame = pd.DataFrame([[sample_id, *range(9)] for sample_id in sample_ids], columns=["sample_id", *snapshot_names])
        window_frame = pd.concat([snapshot_frame, pd.DataFrame([[1] * 45, [2] * 45], columns=summary_names)], axis=1)
        history_frame = pd.concat(
            [window_frame, pd.DataFrame([[index for index in range(125)], [index + 100 for index in range(125)]], columns=[*lag_names, *age_names, *quality_names])],
            axis=1,
        )
        representations = build_representation_bundles(
            snapshot_bundle=FeatureBundle(snapshot_frame, snapshot_names, {"representation": "snapshot"}),
            window_bundle=FeatureBundle(window_frame, [*snapshot_names, *summary_names], {"representation": "window"}),
            history_bundle=FeatureBundle(history_frame, [*snapshot_names, *summary_names, *lag_names, *age_names, *quality_names], {"representation": "history"}),
        )
        audited = build_history_audit_representations(representations=representations, disruption_seed=7)
        self.assertEqual(len(audited["R_pure_lag"].feature_bundle.feature_names), 117)
        self.assertEqual(len(audited["R_meta"].feature_bundle.feature_names), 17)
        self.assertEqual(
            len(audited["R_pure_lag"].feature_bundle.feature_names),
            len(audited["R_pure_lag_disrupted"].feature_bundle.feature_names),
        )
        original = audited["R_pure_lag"].feature_bundle.frame.set_index("sample_id")
        disrupted = audited["R_pure_lag_disrupted"].feature_bundle.frame.set_index("sample_id")
        for sensor in snapshot_names:
            original_values = sorted(original.loc["a", [f"{sensor}__causal_lag_{lag}" for lag in range(1, 13)]].tolist())
            disrupted_values = sorted(disrupted.loc["a", [f"{sensor}__causal_lag_{lag}" for lag in range(1, 13)]].tolist())
            self.assertEqual(original_values, disrupted_values)
        self.assertTrue(audited["R_pure_lag_disrupted"].feature_bundle.metadata["temporal_order_disrupted"])


if __name__ == "__main__":
    unittest.main()
