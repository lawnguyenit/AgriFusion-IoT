from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_representations import build_rq1_nested_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_statistics import (
    add_temporal_order_columns,
    build_paired_contrasts,
    build_per_anchor_losses,
)
from Backend.tests.test_ordered_representation_training import _base_representations_for_test


class RQ1NestedProgressionTests(unittest.TestCase):
    def test_main_chain_is_nested_and_branch_is_separate(self) -> None:
        base, audit = _base_representations_for_test()
        representations = build_rq1_nested_representations(
            base_representations=base,
            audit_representations=audit,
        )
        self.assertEqual(
            [len(representations[key].feature_bundle.feature_names) for key in ("S0_M_t", "S1_X_t", "S2_X_t_HM", "S3_X_t_HX", "S4_X_t_HX_C", "B_M")],
            [1, 9, 21, 117, 162, 13],
        )
        for previous, next_representation in (
            ("S0_M_t", "S1_X_t"),
            ("S1_X_t", "S2_X_t_HM"),
            ("S2_X_t_HM", "S3_X_t_HX"),
            ("S3_X_t_HX", "S4_X_t_HX_C"),
        ):
            previous_names = set(representations[previous].feature_bundle.feature_names)
            next_names = set(representations[next_representation].feature_bundle.feature_names)
            self.assertTrue(previous_names.issubset(next_names))
        self.assertNotIn("causal_history__lag_1_age_hours", representations["S4_X_t_HX_C"].feature_bundle.feature_names)

    def test_paired_losses_use_same_heldout_anchors(self) -> None:
        rows: list[dict[str, object]] = []
        for representation_id, probabilities in (
            ("S0_M_t", (0.55, 0.30, 0.15)),
            ("S1_X_t", (0.20, 0.25, 0.55)),
        ):
            for sample_id, label in (("a", "reference_context_at_anchor"), ("b", "unresolved_environmental_evidence_at_anchor")):
                rows.append(
                    {
                        "representation_id": representation_id,
                        "target_view_id": "temporal_event_3h",
                        "partition": "test",
                        "fold_id": "fold_01",
                        "sample_id": sample_id,
                        "label_true": label,
                        "p_low": probabilities[0],
                        "p_unres": probabilities[1],
                        "p_ref": probabilities[2],
                    }
                )
        predictions = pd.DataFrame(rows)
        row_index = pd.DataFrame(
            {
                "record.id": ["a", "b"],
                "record.node_id": ["node-1", "node-1"],
                "record.segment_id": ["seg-1", "seg-1"],
                "record.ts_sample": [1, 2],
            }
        )
        losses = build_per_anchor_losses(add_temporal_order_columns(predictions, row_index))
        _, summary = build_paired_contrasts(
            losses=losses,
            arrows=(("S0_to_S1", "S0_M_t", "S1_X_t"),),
            block_length=2,
            bootstrap_reps=20,
            seed=7,
        )
        self.assertEqual(len(losses), 4)
        self.assertEqual(int(summary.loc[0, "anchor_count"]), 2)
        self.assertTrue(np.isfinite(float(summary.loc[0, "pooled_delta_log_loss"])))


if __name__ == "__main__":
    unittest.main()
