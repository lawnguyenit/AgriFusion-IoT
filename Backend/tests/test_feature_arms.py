from __future__ import annotations

import unittest

from Backend.Benchmark.dataset_views.configs.feature_arms import (
    BASE_5_FEATURES,
    FULL_9_FEATURES,
    get_feature_arm,
    semantic_arm_for_view,
    validate_allowlist,
)


class FeatureArmTests(unittest.TestCase):
    def test_canonical_arm_sizes_and_membership(self) -> None:
        self.assertEqual(len(get_feature_arm("base_5").feature_names), 5)
        self.assertEqual(len(get_feature_arm("plus_ph").feature_names), 6)
        self.assertEqual(len(get_feature_arm("plus_npk").feature_names), 8)
        self.assertEqual(len(get_feature_arm("full_9").feature_names), 9)
        self.assertEqual(get_feature_arm("base_5").feature_names, BASE_5_FEATURES)
        self.assertEqual(get_feature_arm("full_9").feature_names, FULL_9_FEATURES)

    def test_validate_allowlist_requires_materialized_source_columns(self) -> None:
        self.assertEqual(
            validate_allowlist(arm_id="plus_ph", available_columns=FULL_9_FEATURES),
            get_feature_arm("plus_ph").feature_names,
        )
        with self.assertRaisesRegex(ValueError, "missing columns"):
            validate_allowlist(arm_id="plus_npk", available_columns=BASE_5_FEATURES)

    def test_temporal_views_resolve_to_history_feature_arms(self) -> None:
        self.assertEqual(semantic_arm_for_view("v2_temporal_mini_3h"), "base_5_history_3h")
        self.assertEqual(semantic_arm_for_view("v2_temporal_full_3h"), "full_9_history_3h")


if __name__ == "__main__":
    unittest.main()
