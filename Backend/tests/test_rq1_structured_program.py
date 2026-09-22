from __future__ import annotations

import unittest

import pandas as pd

from Backend.Benchmark.model_suite.analysis.k_window_variants.history import FeatureBundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.rq1_program_representations import (
    _build_acquisition_evidence,
    _build_temporal_context,
    add_persistence_probe_target,
)


class RQ1StructuredProgramTests(unittest.TestCase):
    def test_temporal_context_excludes_history_quality_fields(self) -> None:
        history_names = [
            "causal_history__lag_1_age_hours",
            "causal_history__3h_prior_row_count",
            "causal_history__3h_prior_span_hours",
            "causal_history__3h_max_internal_gap_hours",
            "causal_history__3h_prior_valid_row_count",
            "causal_history__3h_missing_lag_count",
        ]
        history = FeatureBundle(
            frame=pd.DataFrame(
                {
                    "sample_id": ["a"],
                    **{name: [1.0] for name in history_names},
                }
            ),
            feature_names=history_names,
            metadata={},
        )
        row_index = pd.DataFrame(
            {
                "record.id": ["a"],
                "record.node_id": ["node-1"],
                "record.segment_id": ["seg-1"],
                "record.ts_sample": [1000],
                "source_row_position": [0],
                "record.segment_boundary_before": [False],
            }
        )
        window_audit = pd.DataFrame(
            {
                "record.id": ["a"],
                "3h_continuity_reset_count": [0],
                "3h_max_internal_elapsed_gap_sec": [0],
                "3h_actual_window_span_sec": [0],
            }
        )

        _, names = _build_temporal_context(
            history_bundle=history,
            row_index=row_index,
            window_audit=window_audit,
        )

        self.assertIn("causal_history__3h_prior_row_count", names)
        self.assertNotIn("causal_history__3h_prior_valid_row_count", names)
        self.assertNotIn("causal_history__3h_missing_lag_count", names)

    def test_acquisition_block_receives_history_quality_fields(self) -> None:
        snapshot_names = [f"sensor_{index}" for index in range(9)]
        snapshot = FeatureBundle(
            frame=pd.DataFrame({"sample_id": ["a"], **{name: [1.0] for name in snapshot_names}}),
            feature_names=snapshot_names,
            metadata={},
        )
        history = FeatureBundle(
            frame=pd.DataFrame(
                {
                    "sample_id": ["a"],
                    "causal_history__3h_prior_valid_row_count": [2],
                    "causal_history__3h_missing_lag_count": [1],
                }
            ),
            feature_names=[
                "causal_history__3h_prior_valid_row_count",
                "causal_history__3h_missing_lag_count",
            ],
            metadata={},
        )
        audit = pd.DataFrame({"record.id": ["a"], "current_row_complete": [1]})

        _, names, _ = _build_acquisition_evidence(
            snapshot_bundle=snapshot,
            history_bundle=history,
            window_audit=audit,
        )

        self.assertIn("A__causal_history__3h_prior_valid_row_count", names)
        self.assertIn("A__causal_history__3h_missing_lag_count", names)

    def test_persistence_probe_uses_four_clipped_depth_states(self) -> None:
        target = pd.DataFrame({"support_depth_at_anchor": [0, 1, 2, 4]})
        result = add_persistence_probe_target(target)
        self.assertEqual(result["persistence_state"].tolist(), ["d_0", "d_1", "d_2", "d_ge_3"])


if __name__ == "__main__":
    unittest.main()
