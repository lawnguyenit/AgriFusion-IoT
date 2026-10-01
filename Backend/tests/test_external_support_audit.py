from __future__ import annotations

import unittest

import pandas as pd

from Backend.Benchmark.external_support_audit.audit import (
    audit_candidate_support,
    summarize_entity_estimability,
    summarize_entity_support,
)
from Backend.Benchmark.external_support_audit.grid import summarize_candidate_support_by_partition
from Backend.Benchmark.external_support_audit.pipeline import summarize_candidate_gate_rows


class ExternalSupportAuditTests(unittest.TestCase):
    def test_candidate_gate_failure_count_is_an_integer_not_a_boolean(self) -> None:
        support = pd.DataFrame({
            "target_id": ["co", "co", "co", "nox", "nox", "nox"],
            "q_id": ["co_q10"] * 3 + ["nox_q10"] * 3,
            "threshold_scope": ["pooled"] * 6,
            "tail_share": [0.1] * 6,
            "tau_minutes": [120] * 6,
            "support_gate_pass": [True, True, True, True, False, True],
        })
        summary = summarize_candidate_gate_rows(support).set_index("target_id")
        self.assertIn(summary["failing_partition_count"].dtype.kind, "iu")
        self.assertEqual(summary.loc["co", "failing_partition_count"], 0)
        self.assertEqual(summary.loc["nox", "failing_partition_count"], 1)
        self.assertTrue(bool(summary.loc["co", "all_partitions_pass"]))
        self.assertFalse(bool(summary.loc["nox", "all_partitions_pass"]))

    def test_counts_classes_events_and_distinct_line_episodes_by_partition(self) -> None:
        rows = []
        splits = []
        # Each partition has both classes and at least five positive episodes.
        for part_index, partition in enumerate(("train", "validation", "test")):
            start = part_index * 100
            for index in range(49):
                entity = f"line_{index % 5}"
                sample_id = f"{partition}_{index}"
                positive = index % 2 == 0
                rows.append({
                    "sample_id": sample_id,
                    "timestamp": pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(minutes=start + index),
                    "entity_id": entity,
                    "y": int(positive),
                })
                splits.append({
                    "sample_id": sample_id,
                    "partition": partition,
                    "fold_id": "fold1",
                    "timestamp_block_id": sample_id,
                })
        labels = pd.DataFrame(rows)
        split_frame = pd.DataFrame(splits)
        registry = pd.DataFrame([{
            "target_id": "soil_low", "q_id": "soil_low_q10", "threshold_scope": "per_entity",
            "tail_share": 0.1, "tau_minutes": 1440, "label_column": "y",
        }])
        audit = audit_candidate_support(labels=labels, registry=registry, splits=split_frame)
        entity = summarize_entity_support(labels=labels, registry=registry, splits=split_frame)
        self.assertTrue(audit["support_gate_pass"].all())
        self.assertTrue(audit["episode_cluster_count"].ge(5).all())
        self.assertEqual(len(entity), 15)
        self.assertTrue(entity["within_entity_estimable"].all())
        estimability = summarize_entity_estimability(entity)
        self.assertTrue(estimability["entity_claim_estimability_status"].eq("PASS").all())
        self.assertTrue(estimability["entity_discrimination_status"].eq("PASS").all())
        self.assertTrue(estimability["entity_support_adequacy_status"].eq("FAIL").all())

    def test_two_class_entity_can_fail_event_and_episode_support_floors(self) -> None:
        values = [1] * 10 + [0] * 2 + [1] * 10 + [0] * 12
        labels = pd.DataFrame({
            "sample_id": [f"s{i}" for i in range(len(values))],
            "timestamp": pd.date_range("2024-01-01", periods=len(values), freq="h"),
            "entity_id": ["line_3"] * len(values),
            "y": values,
        })
        splits = pd.DataFrame({
            "sample_id": labels["sample_id"],
            "partition": ["test"] * len(values),
            "fold_id": ["fold1"] * len(values),
            "timestamp_block_id": labels["sample_id"],
        })
        registry = pd.DataFrame([{
            "target_id": "soil_low", "q_id": "soil_low_q10", "threshold_scope": "per_entity",
            "tail_share": 0.1, "tau_minutes": 1440, "label_column": "y",
        }])
        support = summarize_entity_support(labels=labels, registry=registry, splits=splits)
        summary = summarize_entity_estimability(support).iloc[0]
        self.assertTrue(bool(support.loc[0, "within_entity_discrimination_estimable"]))
        self.assertFalse(bool(support.loc[0, "within_entity_support_adequate"]))
        self.assertEqual(summary["entity_discrimination_status"], "PASS")
        self.assertEqual(summary["entity_support_adequacy_status"], "FAIL")
        self.assertEqual(summary["support_adequate_entity_count"], 0)

    def test_aggregate_support_and_entity_estimability_are_separate(self) -> None:
        support = pd.DataFrame({
            "target_id": ["soil_low"] * 3,
            "q_id": ["soil_low_q10"] * 3,
            "threshold_scope": ["per_entity"] * 3,
            "tail_share": [0.1] * 3,
            "tau_minutes": [1440] * 3,
            "entity_id": ["line_1", "line_2", "line_3"],
            "partition": ["test"] * 3,
            "within_entity_estimable": [False, False, True],
            "within_entity_discrimination_estimable": [False, False, True],
            "within_entity_support_adequate": [False, False, False],
        })
        result = summarize_entity_estimability(support).iloc[0]
        self.assertEqual(result["entity_claim_estimability_status"], "PARTIAL")
        self.assertEqual(result["entity_discrimination_status"], "PARTIAL")
        self.assertEqual(result["entity_support_adequacy_status"], "FAIL")
        self.assertEqual(result["entity_count"], 3)
        self.assertEqual(result["estimable_entity_count"], 1)
        self.assertEqual(result["support_adequate_entity_count"], 0)
        self.assertEqual(result["non_estimable_entity_ids"], "line_1|line_2")

    def test_partition_grid_is_descriptive_and_has_no_implicit_gate(self) -> None:
        labels = pd.DataFrame({
            "sample_id": [f"s{i}" for i in range(6)],
            "timestamp": pd.date_range("2004-01-01", periods=6, freq="h"),
            "label_co_q10_tau060m": [0, 1, 1, pd.NA, 0, 1],
        }).convert_dtypes()
        registry = pd.DataFrame([{
            "target_id": "co", "q_id": "co_q10", "threshold_scope": "per_entity",
            "tail_share": 0.1, "tau_minutes": 60, "label_column": "label_co_q10_tau060m",
        }])
        splits = pd.DataFrame({
            "sample_id": [f"s{i}" for i in range(6)],
            "fold_id": ["fold_0"] * 6,
            "partition": ["train"] * 2 + ["validation"] * 2 + ["test"] * 2,
        })
        result = summarize_candidate_support_by_partition(labels=labels, registry=registry, splits=splits)
        self.assertEqual(len(result), 3)
        self.assertFalse(result["support_gate_applied"].any())
        self.assertEqual(result.set_index("partition").loc["validation", "unknown_count"], 1)
        self.assertEqual(result.set_index("partition").loc["test", "positive_count"], 1)


if __name__ == "__main__":
    unittest.main()
