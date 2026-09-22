import unittest

import pandas as pd

from Backend.Benchmark.weak_labels.analysis.unres_origin_split import derive_unres_origin_rows


class UnresOriginSplitTests(unittest.TestCase):
    def test_splits_k_fallback_from_auxiliary_fallback(self) -> None:
        temporal_assignments = pd.DataFrame(
            [
                {"sample_id": "s1", "label": "unresolved_environmental_evidence_at_anchor", "source_label": "low_relative_moisture_point", "horizon_id": "3h"},
                {"sample_id": "s2", "label": "unresolved_environmental_evidence_at_anchor", "source_label": "unresolved_environmental_evidence_point", "horizon_id": "3h"},
                {"sample_id": "s3", "label": "reference_context_at_anchor", "source_label": "reference_context_point", "horizon_id": "3h"},
            ]
        )
        temporal_resolutions = pd.DataFrame(
            [
                {"sample_id": "s1", "task_id": "TEMPORAL_ANCHOR", "horizon_id": "3h", "resolved_label": "unresolved_environmental_evidence_at_anchor", "support_depth_at_anchor": 1, "required_k": 3},
                {"sample_id": "s2", "task_id": "TEMPORAL_ANCHOR", "horizon_id": "3h", "resolved_label": "unresolved_environmental_evidence_at_anchor", "support_depth_at_anchor": 0, "required_k": 3},
                {"sample_id": "s3", "task_id": "TEMPORAL_ANCHOR", "horizon_id": "3h", "resolved_label": "reference_context_at_anchor", "support_depth_at_anchor": 0, "required_k": 3},
            ]
        )
        point_resolutions = pd.DataFrame(
            [
                {"sample_id": "s1", "task_id": "POINT", "resolved_label": "low_relative_moisture_point", "resolution_code": "POINT_LOW_RELATIVE_MOISTURE"},
                {"sample_id": "s2", "task_id": "POINT", "resolved_label": "unresolved_environmental_evidence_point", "resolution_code": "POINT_UNRESOLVED_AUXILIARY_POSITIVE"},
                {"sample_id": "s3", "task_id": "POINT", "resolved_label": "reference_context_point", "resolution_code": "POINT_REFERENCE_CONTEXT"},
            ]
        )
        rule_firings = pd.DataFrame(
            [
                {"sample_id": "s1", "task_id": "POINT", "rule_id": "LOW_RELATIVE_MOISTURE", "evidence_state": "POSITIVE", "evidence_value": 59.0, "threshold_value": 59.96, "comparison_operator": "<="},
                {"sample_id": "s2", "task_id": "POINT", "rule_id": "LOW_RELATIVE_MOISTURE", "evidence_state": "NEGATIVE", "evidence_value": 61.0, "threshold_value": 59.96, "comparison_operator": "<="},
                {"sample_id": "s2", "task_id": "POINT", "rule_id": "THERMAL_CONTEXT", "evidence_state": "POSITIVE", "evidence_value": 3.0, "threshold_value": 2.5, "comparison_operator": ">="},
                {"sample_id": "s3", "task_id": "POINT", "rule_id": "LOW_RELATIVE_MOISTURE", "evidence_state": "NEGATIVE", "evidence_value": 61.0, "threshold_value": 59.96, "comparison_operator": "<="},
            ]
        )
        temporal_evidence = pd.DataFrame(
            [{"sample_id": sample_id, "horizon_id": "3h", "representation_history_status": "ELIGIBLE"} for sample_id in ("s1", "s2", "s3")]
        )

        result = derive_unres_origin_rows(
            temporal_assignments=temporal_assignments,
            temporal_resolutions=temporal_resolutions,
            point_resolutions=point_resolutions,
            rule_firings=rule_firings,
            temporal_evidence=temporal_evidence,
        )

        origins = dict(zip(result["sample_id"], result["unres_origin"], strict=True))
        self.assertEqual(origins, {"s1": "UNRES_K", "s2": "UNRES_A", "s3": "NOT_UNRES"})
        self.assertEqual(result.loc[result["sample_id"].eq("s1"), "origin_formula"].iloc[0], "M_t <= Q and d_t < K")
        self.assertEqual(result.loc[result["sample_id"].eq("s2"), "aux_positive_rule_ids"].iloc[0], "THERMAL_CONTEXT")


if __name__ == "__main__":
    unittest.main()
