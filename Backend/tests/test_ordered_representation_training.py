from __future__ import annotations

import unittest

import pandas as pd

from Backend.Benchmark.model_suite.analysis.k_window_variants.history import FeatureBundle
from Backend.Benchmark.model_suite.analysis.k_window_variants.representations import build_representation_bundles
from Backend.Benchmark.model_suite.analysis.k_window_variants.robustness_features import build_history_audit_representations
from Backend.Benchmark.model_suite.analysis.k_window_variants.ordered_representations import (
    ORDERED_REPRESENTATION_IDS,
    build_ordered_representation_bundles,
)


class OrderedRepresentationTests(unittest.TestCase):
    def test_requested_feature_counts_and_group_exclusion(self) -> None:
        base, audit = _base_representations_for_test()
        ordered = build_ordered_representation_bundles(
            base_representations=base,
            audit_representations=audit,
        )
        self.assertEqual(tuple(ordered), ORDERED_REPRESENTATION_IDS)
        self.assertEqual([len(ordered[key].feature_bundle.feature_names) for key in ordered], [1, 9, 13, 117, 162])
        self.assertFalse(ordered["X_history_context"].feature_bundle.metadata["acquisition_metadata_included"])
        self.assertNotIn("causal_history__lag_1_age_hours", ordered["X_history_context"].feature_bundle.feature_names)


def _base_representations_for_test():
    sample_ids = ["a", "b"]
    snapshot_names = [
        "npk.soil_moisture_pct",
        *[f"sensor_{index}" for index in range(8)],
    ]
    summary_names = [
        f"sensor_{index}__3h_stat_{stat}"
        for index in range(9)
        for stat in range(5)
    ]
    lag_names = [
        f"{sensor}__causal_lag_{lag}"
        for lag in range(1, 13)
        for sensor in snapshot_names
    ]
    age_names = [f"causal_history__lag_{lag}_age_hours" for lag in range(1, 13)]
    quality_names = [f"causal_history__3h_quality_{index}" for index in range(5)]
    snapshot_frame = pd.DataFrame(
        [[sample_id, *range(9)] for sample_id in sample_ids],
        columns=["sample_id", *snapshot_names],
    )
    window_frame = pd.concat(
        [
            snapshot_frame,
            pd.DataFrame([[1] * 45, [2] * 45], columns=summary_names),
        ],
        axis=1,
    )
    history_frame = pd.concat(
        [
            window_frame,
            pd.DataFrame(
                [[1] * 125, [2] * 125],
                columns=[*lag_names, *age_names, *quality_names],
            ),
        ],
        axis=1,
    )
    base = build_representation_bundles(
        snapshot_bundle=FeatureBundle(snapshot_frame, snapshot_names, {"representation": "snapshot"}),
        window_bundle=FeatureBundle(window_frame, [*snapshot_names, *summary_names], {"representation": "window"}),
        history_bundle=FeatureBundle(history_frame, [*snapshot_names, *summary_names, *lag_names, *age_names, *quality_names], {"representation": "history"}),
    )
    audit = build_history_audit_representations(representations=base, disruption_seed=7)
    return base, audit


if __name__ == "__main__":
    unittest.main()
