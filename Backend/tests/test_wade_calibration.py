from __future__ import annotations

import unittest

import pandas as pd

from Backend.Benchmark.model_suite.analysis.wade_calibration.representations import build_representations
from Backend.Benchmark.model_suite.analysis.wade_calibration.worlds import WORLD_IDS, generate_world


class WadeCalibrationTests(unittest.TestCase):
    def test_world_generation_is_deterministic_and_sequence_disjoint(self) -> None:
        first = generate_world(world_id="W_H", n_samples=1_000, data_seed=41)
        second = generate_world(world_id="W_H", n_samples=1_000, data_seed=41)
        pd.testing.assert_frame_equal(first.frame, second.frame)
        partitions = {
            partition: set(first.frame.loc[first.frame["partition"] == partition, "sequence_id"])
            for partition in ("train", "validation", "test")
        }
        self.assertFalse(partitions["train"] & partitions["validation"])
        self.assertFalse(partitions["train"] & partitions["test"])
        self.assertFalse(partitions["validation"] & partitions["test"])

    def test_all_worlds_have_shared_contract_and_three_classes(self) -> None:
        for world_id in WORLD_IDS:
            dataset = generate_world(world_id=world_id, n_samples=1_000, data_seed=100 + len(world_id))
            self.assertEqual(set(dataset.frame["label"].unique()), {"LOW", "UNRES", "REF"})
            representations = build_representations(dataset=dataset, disruption_seed=7)
            self.assertEqual(len(representations["S1_snapshot"].feature_names), 9)
            self.assertEqual(len(representations["S3_history"].feature_names), 27)
            self.assertEqual(len(representations["R_reduced"].feature_names), 11)
            self.assertEqual(len(representations["R_full"].feature_names), 13)
            self.assertEqual(len(representations["A_only"].feature_names), 3)

    def test_history_disruption_changes_history_but_not_anchor_identity(self) -> None:
        dataset = generate_world(world_id="W_H", n_samples=1_000, data_seed=55)
        representations = build_representations(dataset=dataset, disruption_seed=8)
        original = representations["S3_history"].frame.set_index("sample_id")
        disrupted = representations["S3_history_disrupted"].frame.set_index("sample_id")
        self.assertTrue((original["M_t_lag1"] != disrupted["M_t_lag1"]).any())
        self.assertEqual(original.index.tolist(), disrupted.index.tolist())

    def test_acquisition_world_contains_known_shortcut(self) -> None:
        dataset = generate_world(world_id="W_A", n_samples=4_000, data_seed=66)
        gap_rates = dataset.frame.groupby("label", sort=True)["acq_gap_flag"].mean()
        self.assertGreater(float(gap_rates["LOW"]), float(gap_rates["REF"]) + 0.50)

    def test_rule_world_oracle_is_exact_by_construction(self) -> None:
        dataset = generate_world(world_id="W_R", n_samples=1_000, data_seed=77)
        self.assertTrue((dataset.frame["label"] == dataset.frame["oracle_label"]).all())


if __name__ == "__main__":
    unittest.main()
