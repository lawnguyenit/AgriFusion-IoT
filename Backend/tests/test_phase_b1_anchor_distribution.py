from __future__ import annotations

import unittest

import pandas as pd

from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.anchor_audit import (
    _summarize_projected_anchors,
)
from Backend.Benchmark.weak_labels.lifecycle.phase_b_contract.distribution_audit import (
    _temporal_resolution,
)


class PhaseB1AnchorDistributionTests(unittest.TestCase):
    def test_support_counts_are_split_specific(self) -> None:
        projected = pd.DataFrame(
            [
                {
                    "q_contract_id": "Q10",
                    "threshold_value": 59.96,
                    "persistence_k": 3,
                    "fold_policy_id": "E1_PRIMARY_7D_V1",
                    "fold_id": "fold_01",
                    "split_role": "train",
                    "window_horizon_hours": 3,
                    "observed_low_run_id": "run-a",
                    "anchor_dependency_admissible": True,
                    "purge_excluded": False,
                    "boundary_excluded": False,
                    "cross_split_anchor": False,
                    "cross_deployment_anchor": False,
                    "observed_run_crossing_audit": False,
                },
                {
                    "q_contract_id": "Q10",
                    "threshold_value": 59.96,
                    "persistence_k": 3,
                    "fold_policy_id": "E1_PRIMARY_7D_V1",
                    "fold_id": "fold_01",
                    "split_role": "validation",
                    "window_horizon_hours": 3,
                    "observed_low_run_id": "run-b",
                    "anchor_dependency_admissible": True,
                    "purge_excluded": False,
                    "boundary_excluded": False,
                    "cross_split_anchor": False,
                    "cross_deployment_anchor": False,
                    "observed_run_crossing_audit": False,
                },
            ]
        )
        summary = _summarize_projected_anchors(projected)
        self.assertEqual(set(summary["event_count"]), {1})
        self.assertEqual(set(summary["persistent_anchor_count"]), {1})

    def test_future_run_crossing_does_not_invalidate_admissible_anchor(self) -> None:
        row = pd.Series(
            {
                "anchor_dependency_admissible": True,
                "point_resolution": "LOW",
                "run_length": 3,
                "persistence_k": 3,
                "observed_run_crosses_split": True,
            }
        )
        self.assertEqual(_temporal_resolution(row), "TEMPORAL_PERSISTENT_LOW")


if __name__ == "__main__":
    unittest.main()
